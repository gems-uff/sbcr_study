import os
import subprocess
import torch
import shutil
import tempfile
import uuid
from transformers import RobertaTokenizer, T5ForConditionalGeneration
from typing import List
from torch import nn
import warnings


warnings.filterwarnings("ignore")

class MergeInference:
    """
    Wraps a trained MergeGen model to resolve one merge conflict at a time: tokenization,
    structured representation with `git merge-file`, generation and decoding, in one process.
    """
    def __init__(self, model_path: str = "best_model.pt"):
        """
        Loads the tokenizer and the trained model. Both paths are relative to the working
        directory, which must hold `codet5-small-local`.

        Args:
            model_path (str): path of the trained model (.pt).
        """
        self.model_type = './codet5-small-local'
        # self.model_type = './codet5-base'
        self.device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
        print(f"Using device: {self.device}")

        # the tokenizer with the structural tokens of MergeGen
        # self.tokenizer = RobertaTokenizer.from_pretrained(self.model_type)
        self.tokenizer = RobertaTokenizer.from_pretrained(self.model_type)
        brackets_tokens = ['<lbra>', '<mbra>', '<rbra>']
        self.tokenizer.add_tokens(brackets_tokens)
        

        # the same wrapper as in training, to load the weights
        class MergeT5(nn.Module):
            def __init__(self, model_type, tokenizer_instance):
                super(MergeT5, self).__init__()
                self.t5 = T5ForConditionalGeneration.from_pretrained(model_type)
                self.t5.resize_token_embeddings(len(tokenizer_instance))

        wrapper_model = MergeT5(self.model_type, self.tokenizer)
        wrapper_model.load_state_dict(torch.load(model_path, map_location=self.device))
        
        self.model = wrapper_model.t5
        self.model.to(self.device)
        self.model.eval()

        
        # lengths and beams of the original configuration
        self.max_conflict_length = 500
        self.max_resolve_length = 200
        self.num_beams = 3
        
        self.lbra_token = '<lbra>'
        self.rbra_token = '<rbra>'

    def _git_merge_single(self, tokens_base: List[str], tokens_a: List[str], tokens_b: List[str]) -> List[str]:
        """
        Builds the structured representation of the conflict with `git merge-file --diff3`
        over one token per line, the steps of `dataset_parallel.py`.
        """
        temp_dir = os.path.join(tempfile.gettempdir(), f'mergegen-inference-{uuid.uuid4()}')
        os.makedirs(temp_dir, exist_ok=True)

        try:
            with open(os.path.join(temp_dir, 'base'), 'w', encoding='utf-8') as f:
                f.write('\n'.join(tokens_base))
            with open(os.path.join(temp_dir, 'a'), 'w', encoding='utf-8') as f:
                f.write('\n'.join(tokens_a))
            with open(os.path.join(temp_dir, 'b'), 'w', encoding='utf-8') as f:
                f.write('\n'.join(tokens_b))
            
            merge_file_path = os.path.join(temp_dir, 'merge')
            cmd = f'git merge-file -L a -L base -L b {os.path.join(temp_dir, "a")} {os.path.join(temp_dir, "base")} {os.path.join(temp_dir, "b")} --diff3 -p > {merge_file_path}'
            subprocess.run(cmd, shell=True, check=False)
            
            with open(merge_file_path, 'r', encoding='utf-8') as f:
                merge_res = [x.strip() for x in f.readlines() if x.strip()]

            format_ids = [k for k, x in enumerate(merge_res) if x in ['<<<<<<< a', '>>>>>>> b', '||||||| base', '=======']]
            
            final_tokens = []
            start = 0
            for k in range(0, len(format_ids), 4):
                context_tokens = merge_res[start:format_ids[k]]
                a_tokens = merge_res[format_ids[k] + 1:format_ids[k + 1]]
                base_tokens = merge_res[format_ids[k + 1] + 1:format_ids[k + 2]]
                b_tokens = merge_res[format_ids[k + 2] + 1:format_ids[k + 3]]
                start = format_ids[k + 3] + 1

                final_tokens.extend(context_tokens)
                final_tokens.append(self.lbra_token)
                final_tokens.extend(a_tokens)
                final_tokens.append(self.tokenizer.sep_token)
                final_tokens.extend(base_tokens)
                final_tokens.append(self.tokenizer.sep_token)
                final_tokens.extend(b_tokens)
                final_tokens.append(self.rbra_token)

            if start < len(merge_res):
                final_tokens.extend(merge_res[start:])
            
            return [self.tokenizer.bos_token] + final_tokens + [self.tokenizer.eos_token]

        finally:
            shutil.rmtree(temp_dir, ignore_errors=True)
            
    def _pad_sequence(self, token_ids: List[int], max_length: int, pad_id: int) -> List[int]:
        """Pads or cuts the token ids to `max_length`."""
        if len(token_ids) > max_length:
            return token_ids[:max_length]
        return token_ids + [pad_id] * (max_length - len(token_ids))

    def generate_resolution(self, base_code: str, version_a: str, version_b: str) -> str:
        """
        Generates a resolution from the base and the two conflicting versions.

        Its decoding (`max_new_tokens`, early stopping) is not that of `run_mergegen.py`.
        `mergegen/jit_inference.py` does not call this method: it reproduces the decoding
        of `run_mergegen.py`.
        """
        base_tokens = self.tokenizer.tokenize(' '.join(base_code.split()))
        a_tokens = self.tokenizer.tokenize(' '.join(version_a.split()))
        b_tokens = self.tokenizer.tokenize(' '.join(version_b.split()))
        
        conflict_tokens = self._git_merge_single(base_tokens, a_tokens, b_tokens)
        
        conflict_ids = self.tokenizer.convert_tokens_to_ids(conflict_tokens)
        padded_input = self._pad_sequence(conflict_ids, self.max_conflict_length, self.tokenizer.pad_token_id)
        
        input_tensor = torch.tensor([padded_input], device=self.device)
        attention_mask = (input_tensor != self.tokenizer.pad_token_id).long()
        
        with torch.no_grad():
            output_ids = self.model.generate(
                input_ids=input_tensor,
                attention_mask=attention_mask,
                max_new_tokens=self.max_resolve_length,
                num_beams=self.num_beams,
                early_stopping=True
            )
        
        resolution = self.tokenizer.decode(output_ids[0], skip_special_tokens=True)
        return resolution


if __name__ == '__main__':
    import argparse
    p = argparse.ArgumentParser(description="Resolves an example conflict with a trained MergeGen model.")
    p.add_argument("--model", default="best_model.pt", help="trained model (.pt), relative to the working directory")
    model_path = p.parse_args().model
    inference_tool = MergeInference(model_path=model_path)
    base_code = ""
    a_code = """        applyOnClickAttribute();
    }

    public View.OnClickListener getOnClickListener() {
      return onClickListener;
        """
    b_code = """

        applyTagAttribute();
        applyOnClickAttribute();
        """
    print("--- Example conflict ---")
    print(f"Base:      {base_code}")
    print(f"Version A: {a_code}")
    print(f"Version B: {b_code}")
    print("------------------------")
    print(f"\nGenerated resolution: {inference_tool.generate_resolution(base_code, a_code, b_code)}")
