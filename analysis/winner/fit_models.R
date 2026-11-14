# Models of the characteristics that predict the winner.
#
# Reads `conflicts.csv` of `build_table.py` (one row per conflict of the combination subset of the
# test partition of partition 1). Fixed effects, the same in every model: the three predictors
# (`imbalance`, `input_above_500`, `outside_ascii_any`) and the controls `log_size` and `dataset`.
# `dataset` has five levels, Dataset1 the reference, and stands for language and source together.
#
# Models:
#   main           linear mixed model of `difference` (SBCR − MergeGen), random intercept per project;
#   logistic       logistic mixed model of `sbcr_wins`, ties left out, random intercept per project;
#   within_limits  the main model without the conflicts above SBCR's 20,000-character limit;
#   merge_nested   the main model with merge nested in project.
#
# Everything is fitted by maximum likelihood, so that the likelihood-ratio tests and the profile
# intervals refer to the same likelihood. Per model and predictor: estimate, 95% profile-likelihood
# interval, p of the likelihood-ratio test that drops it, Holm over the predictors, and whether the
# sign is the expected one (negative for the imbalance, positive for the others).
#
# Cells of the routing rule (main model): input above 500 tokens or not, letters outside ASCII or
# not, balanced versions (imbalance <= 0.1) or not. In each cell, the mean of the fixed-effect
# predictions over its conflicts, with a Wald 95% interval from the covariance of the fixed effects.
#
# Predictive capacity: marginal and conditional R² (Nakagawa and Schielzeth) of the linear models,
# and the AUC of the logistic model, from the fixed effects alone and with the project effects.
#
# With `--two`, the models leave out `outside_ascii_any` and keep the imbalance and the token limit,
# Holm runs over the two, and the cells are defined by the token limit and the balance only.
#
# Outputs, in the folder given or in `--out`: `coefficients.csv`, `cells.csv`, `fit.csv` and
# `fit_models.log` (model summaries, warnings and the session information).
#
# Runs in the conda environment `winner-model`:
#   conda run -n winner-model Rscript analysis/winner/fit_models.R <folder of build_table.py> [--two] [--out=<folder>]

suppressPackageStartupMessages(library(lme4))

USAGE <- "usage: fit_models.R <folder with conflicts.csv> [--two] [--out=<folder>]"
args <- commandArgs(trailingOnly = TRUE)
flags <- args[startsWith(args, "--")]
if (length(args) - length(flags) != 1 || !all(flags == "--two" | startsWith(flags, "--out=")) ||
    sum(startsWith(flags, "--out=")) > 1) stop(USAGE)
folder <- args[!startsWith(args, "--")]
two <- "--two" %in% flags
out <- if (any(startsWith(flags, "--out="))) sub("^--out=", "", flags[startsWith(flags, "--out=")]) else folder
dir.create(out, showWarnings = FALSE, recursive = TRUE)
log_path <- file.path(out, "fit_models.log")
log_con <- file(log_path, open = "wt")
say <- function(...) {
  text <- paste0(...)
  cat(text, "\n")
  writeLines(text, log_con)
}
show <- function(x) {
  text <- capture.output(print(x))
  cat(text, sep = "\n")
  writeLines(text, log_con)
}

BALANCED <- 0.1
PREDICTORS <- c("imbalance", "input_above_500TRUE", "outside_ascii_anyTRUE")
EXPECTED <- c(imbalance = -1, input_above_500TRUE = 1, outside_ascii_anyTRUE = 1)
DROP <- c(imbalance = "imbalance", input_above_500TRUE = "input_above_500",
          outside_ascii_anyTRUE = "outside_ascii_any")
FIXED <- "imbalance + input_above_500 + outside_ascii_any + log_size + dataset"
CELL_BY <- c("input_above_500", "outside_ascii_any", "balanced")
if (two) {
  PREDICTORS <- c("imbalance", "input_above_500TRUE")
  FIXED <- "imbalance + input_above_500 + log_size + dataset"
  CELL_BY <- c("input_above_500", "balanced")
}

t <- read.csv(file.path(folder, "conflicts.csv"), stringsAsFactors = FALSE)
for (col in c("input_above_500", "outside_ascii_any", "out_of_limits")) t[[col]] <- as.logical(t[[col]])
t$dataset <- factor(t$dataset, levels = c("dataset1", "dataset2_Java", "dataset2_CSharp",
                                          "dataset2_JavaScript", "dataset2_TypeScript"))
if (anyNA(t[, c("difference", "imbalance", "input_above_500", "outside_ascii_any", "log_size",
                "dataset", "project", "merge")])) stop("missing values in conflicts.csv")
say("conflicts: ", nrow(t), "   projects: ", length(unique(t$project)))

warnings_of <- list()
# `data` is the name of a data frame of the global environment. The call stored in the model
# names it, so that the refits of the profile and of the likelihood-ratio tests find it.
fit <- function(name, formula, data, logistic = FALSE) {
  w <- character()
  call <- if (logistic) {
    bquote(glmer(.(formula), data = .(as.name(data)), family = binomial,
                 control = glmerControl(optimizer = "bobyqa", optCtrl = list(maxfun = 1e5))))
  } else {
    bquote(lmer(.(formula), data = .(as.name(data)), REML = FALSE))
  }
  m <- withCallingHandlers(eval(call, globalenv()),
    warning = function(cond) { w <<- c(w, conditionMessage(cond)); invokeRestart("muffleWarning") })
  warnings_of[[name]] <<- w
  m
}

# `devtol` is the deviance by which the profile may fall below the fit before `profile` stops.
# Its default, 1e-9, stops the profile of the logistic model, which finds a deviance 0.00024 lower
# than the fit of `bobyqa`. bobyqa reaches the highest likelihood of the optimizers of `lme4`
# tried (bobyqa, bobyqa with rhoend 1e-10, nloptwrap with tolerances 1e-12, and the default
# bobyqa then Nelder-Mead), and their fixed effects agree to four decimals, so the gap is
# numerical. The 95% interval is where the deviance rises by 3.84.
tests <- function(name, m, devtol = 1e-9) {
  ci <- confint(m, parm = PREDICTORS, method = "profile", devtol = devtol)
  p <- sapply(PREDICTORS, function(term) {
    reduced <- update(m, as.formula(paste(". ~ . -", DROP[[term]])))
    anova(reduced, m)[["Pr(>Chisq)"]][2]
  })
  est <- fixef(m)[PREDICTORS]
  data.frame(model = name, term = PREDICTORS, estimate = est, ci_low = ci[PREDICTORS, 1],
             ci_high = ci[PREDICTORS, 2], p_lrt = p, p_holm = p.adjust(p, method = "holm"),
             expected_sign = EXPECTED[PREDICTORS], sign_matches = sign(est) == EXPECTED[PREDICTORS],
             row.names = NULL)
}

r2 <- function(m) {
  var_f <- var(as.vector(model.matrix(m) %*% fixef(m)))
  var_r <- sum(sapply(VarCorr(m), function(v) v[1, 1]))
  var_e <- sigma(m)^2
  c(r2_marginal = var_f / (var_f + var_r + var_e), r2_conditional = (var_f + var_r) / (var_f + var_r + var_e))
}

auc <- function(score, y) {
  r <- rank(score)
  n1 <- sum(y == 1)
  n0 <- sum(y == 0)
  (sum(r[y == 1]) - n1 * (n1 + 1) / 2) / (n1 * n0)
}

describe <- function(name, m, data) {
  w <- warnings_of[[name]]
  data.frame(model = name, n = nrow(data), projects = length(unique(data$project)),
             singular = isSingular(m), warnings = if (length(w)) paste(w, collapse = " | ") else "",
             project_sd = attr(VarCorr(m)$project, "stddev"))
}

coefs <- list()
fits <- list()

# main
f_main <- as.formula(paste("difference ~", FIXED, "+ (1 | project)"))
m_main <- fit("main", f_main, "t")
say("\n=== main: linear mixed model of SBCR − MergeGen ===")
show(summary(m_main))
coefs$main <- tests("main", m_main)
fits$main <- cbind(describe("main", m_main, t), t(r2(m_main)), auc_fixed = NA, auc_conditional = NA)

# logistic, ties left out
tw <- t[!is.na(t$sbcr_wins), ]
f_logit <- as.formula(paste("sbcr_wins ~", FIXED, "+ (1 | project)"))
m_logit <- fit("logistic", f_logit, "tw", logistic = TRUE)
say("\n=== logistic: logistic mixed model of SBCR winning, ties left out ===")
show(summary(m_logit))
coefs$logistic <- tests("logistic", m_logit, devtol = 1e-3)
fits$logistic <- cbind(describe("logistic", m_logit, tw), r2_marginal = NA, r2_conditional = NA,
                       auc_fixed = auc(predict(m_logit, re.form = NA), tw$sbcr_wins),
                       auc_conditional = auc(predict(m_logit), tw$sbcr_wins))

# without the conflicts above SBCR's limit
tl <- t[!t$out_of_limits, ]
m_lim <- fit("within_limits", f_main, "tl")
say("\n=== within_limits: main model without the conflicts above SBCR's limit ===")
show(summary(m_lim))
coefs$within_limits <- tests("within_limits", m_lim)
fits$within_limits <- cbind(describe("within_limits", m_lim, tl), t(r2(m_lim)), auc_fixed = NA, auc_conditional = NA)

# merge nested in project
f_nest <- as.formula(paste("difference ~", FIXED, "+ (1 | project/merge)"))
m_nest <- fit("merge_nested", f_nest, "t")
say("\n=== merge_nested: main model with merge nested in project ===")
show(summary(m_nest))
coefs$merge_nested <- tests("merge_nested", m_nest)
fits$merge_nested <- cbind(describe("merge_nested", m_nest, t), t(r2(m_nest)), auc_fixed = NA, auc_conditional = NA)

coefficients <- do.call(rbind, coefs)
fit_table <- do.call(rbind, lapply(fits, function(x) { x$project_sd <- as.numeric(x$project_sd); x }))
write.csv(coefficients, file.path(out, "coefficients.csv"), row.names = FALSE)
write.csv(fit_table, file.path(out, "fit.csv"), row.names = FALSE)

# cells of the routing rule, main model
t$balanced <- t$imbalance <= BALANCED
X <- model.matrix(m_main)
V <- as.matrix(vcov(m_main))
b <- fixef(m_main)
cells <- do.call(rbind, lapply(split(seq_len(nrow(t)), t[CELL_BY]),
  function(i) {
    if (!length(i)) return(NULL)
    x <- colMeans(X[i, , drop = FALSE])
    pred <- sum(x * b)
    se <- sqrt(as.numeric(t(x) %*% V %*% x))
    w <- t$sbcr_wins[i]
    do.call(data.frame, c(as.list(t[i[1], CELL_BY]),
               list(n = length(i), predicted = pred, se = se,
                    ci_low = pred - qnorm(0.975) * se, ci_high = pred + qnorm(0.975) * se,
                    observed = mean(t$difference[i]), sbcr_wins_share = mean(w == 1, na.rm = TRUE),
                    ties = sum(is.na(w)))))
  }))
cells$sbcr_better_ci_above_zero <- cells$ci_low > 0
write.csv(cells, file.path(out, "cells.csv"), row.names = FALSE)

say("\n=== coefficients of the ", if (two) "two" else "three", " predictors ===")
show(coefficients)
say("\n=== fit ===")
show(fit_table)
say("\n=== cells of the routing rule (main model) ===")
show(cells)
say("\nsome cell with SBCR better and its interval above zero: ", any(cells$sbcr_better_ci_above_zero))
say("\n=== session ===")
show(sessionInfo())
close(log_con)
