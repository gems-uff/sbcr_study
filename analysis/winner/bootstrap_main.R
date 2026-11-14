# Bootstrap by project of the main model of `fit_models.R`.
#
# The profile intervals of the main model, a linear mixed model of the difference SBCR − MergeGen,
# assume normal residuals with constant variance. The response is bounded between −1 and 1 and
# about a fifth of it is exactly 0 (the ties). This script resamples the projects with
# replacement, keeping all conflicts of each drawn project, refits the main model on each
# resample and reports percentile 95% intervals of the three predictors, which do not need that
# assumption. A project drawn twice enters as two levels of the random effect.
#
# Same data, formula and fit as the main model of `fit_models.R`: `conflicts.csv` of
# `build_table.py`, fixed effects `imbalance + input_above_500 + outside_ascii_any + log_size +
# dataset`, random intercept per project, maximum likelihood. The seed, 881238410, was drawn with
# `secrets.randbelow` before the run.
#
# With `--two`, the main model leaves out `outside_ascii_any`, as `fit_models.R --two` does, and the
# resamples are those of the same seed.
#
# Outputs, in the folder given or in the one of `--out`, which also holds the `coefficients.csv` of
# `fit_models.R`: `bootstrap_main.csv` (per predictor: estimate of the main model, mean and standard
# deviation over the resamples, percentile interval, and the profile interval of `coefficients.csv`
# beside it), `bootstrap_main_draws.csv` (the estimates of every resample) and `bootstrap_main.log`
# (warnings and the session information).
#
# Runs in the conda environment `winner-model`, after `fit_models.R`:
#   conda run -n winner-model Rscript analysis/winner/bootstrap_main.R <folder of build_table.py> [resamples] [--two] [--out=<folder>]

suppressPackageStartupMessages(library(lme4))

USAGE <- "usage: bootstrap_main.R <folder with conflicts.csv> [resamples] [--two] [--out=<folder>]"
args <- commandArgs(trailingOnly = TRUE)
flags <- args[startsWith(args, "--")]
positional <- args[!startsWith(args, "--")]
if (!length(positional) %in% 1:2 || !all(flags == "--two" | startsWith(flags, "--out=")) ||
    sum(startsWith(flags, "--out=")) > 1) stop(USAGE)
folder <- positional[1]
B <- if (length(positional) == 2) as.integer(positional[2]) else 2000L
two <- "--two" %in% flags
out <- if (any(startsWith(flags, "--out="))) sub("^--out=", "", flags[startsWith(flags, "--out=")]) else folder
dir.create(out, showWarnings = FALSE, recursive = TRUE)
SEED <- 881238410L
log_con <- file(file.path(out, "bootstrap_main.log"), open = "wt")
say <- function(...) {
  text <- paste0(...)
  cat(text, "\n")
  writeLines(text, log_con)
}

PREDICTORS <- c("imbalance", "input_above_500TRUE", "outside_ascii_anyTRUE")
FORMULA <- difference ~ imbalance + input_above_500 + outside_ascii_any + log_size + dataset + (1 | project)
if (two) {
  PREDICTORS <- c("imbalance", "input_above_500TRUE")
  FORMULA <- difference ~ imbalance + input_above_500 + log_size + dataset + (1 | project)
}

d <- read.csv(file.path(folder, "conflicts.csv"), stringsAsFactors = FALSE)
for (col in c("input_above_500", "outside_ascii_any")) d[[col]] <- as.logical(d[[col]])
d$dataset <- factor(d$dataset, levels = c("dataset1", "dataset2_Java", "dataset2_CSharp",
                                          "dataset2_JavaScript", "dataset2_TypeScript"))
if (anyNA(d[, c("difference", "imbalance", "input_above_500", "outside_ascii_any", "log_size",
                "dataset", "project")])) stop("missing values in conflicts.csv")

main <- lmer(FORMULA, data = d, REML = FALSE)
estimate <- fixef(main)[PREDICTORS]
say("conflicts: ", nrow(d), "   projects: ", length(unique(d$project)), "   resamples: ", B, "   seed: ", SEED)

rows_of <- split(seq_len(nrow(d)), d$project)
projects <- names(rows_of)
RNGkind("Mersenne-Twister", "Inversion", "Rejection")
set.seed(SEED)
draws <- matrix(NA_real_, nrow = B, ncol = length(PREDICTORS), dimnames = list(NULL, PREDICTORS))
warned <- character()
singular <- 0L
for (b in seq_len(B)) {
  drawn <- sample(projects, length(projects), replace = TRUE)
  rows <- rows_of[drawn]
  bd <- d[unlist(rows, use.names = FALSE), ]
  bd$project <- rep(sprintf("p%04d", seq_along(drawn)), lengths(rows))
  m <- withCallingHandlers(lmer(FORMULA, data = bd, REML = FALSE),
    warning = function(cond) {
      warned <<- c(warned, sprintf("resample %d: %s", b, conditionMessage(cond)))
      invokeRestart("muffleWarning")
    },
    message = function(cond) {
      warned <<- c(warned, sprintf("resample %d: %s", b, trimws(conditionMessage(cond))))
      invokeRestart("muffleMessage")
    })
  if (isSingular(m)) singular <- singular + 1L
  # a predictor absent from a resample is dropped by lmer and stays NA here
  f <- fixef(m)
  draws[b, ] <- f[PREDICTORS]
  if (b %% 200 == 0) say("resample ", b, " of ", B)
}

profile <- read.csv(file.path(out, "coefficients.csv"), stringsAsFactors = FALSE)
profile <- profile[profile$model == "main", ]
result <- data.frame(
  term = PREDICTORS, estimate = estimate,
  boot_mean = colMeans(draws, na.rm = TRUE), boot_sd = apply(draws, 2, sd, na.rm = TRUE),
  boot_low = apply(draws, 2, quantile, probs = 0.025, na.rm = TRUE, names = FALSE),
  boot_high = apply(draws, 2, quantile, probs = 0.975, na.rm = TRUE, names = FALSE),
  profile_low = profile$ci_low[match(PREDICTORS, profile$term)],
  profile_high = profile$ci_high[match(PREDICTORS, profile$term)],
  resamples = B, missing = colSums(is.na(draws)), singular = singular, seed = SEED,
  row.names = NULL)
write.csv(result, file.path(out, "bootstrap_main.csv"), row.names = FALSE)
write.csv(data.frame(resample = seq_len(B), draws), file.path(out, "bootstrap_main_draws.csv"),
          row.names = FALSE)

say("\n=== bootstrap by project, main model ===")
text <- capture.output(print(result))
cat(text, sep = "\n")
writeLines(text, log_con)
say("\nresamples with a warning or message: ", length(unique(sub(":.*", "", warned))))
if (length(warned)) writeLines(warned, log_con)
say("\n=== session ===")
writeLines(capture.output(print(sessionInfo())), log_con)
close(log_con)
