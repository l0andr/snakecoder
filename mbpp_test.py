import argparse
import tqdm
import os

from llama_cpp import Llama

def construct_prompt(input_file:str):
    with open(input_file, "r") as f:
        lines = f.readlines()
    prompt = ""
    #prompt start from first line with "def" and finish with first line with "pass" and contain all lines between them
    start_found = False
    end_found = False
    for l in lines:
        if l.startswith("def"):
            start_found = True
        if start_found and "pass" in l:
            break
        if start_found:
            prompt += l
    tests_lines = ""
    #lines after first pass are lines of test cases and should be added to test_lines
    start_found = False
    end_found = False
    for l in lines:
        if l.startswith("def"):
            start_found = True
        if start_found and not end_found and "pass" in l:
            end_found = True
            continue
        if not end_found:
            continue
        else:
            tests_lines += l
    return prompt, tests_lines

if __name__ ==  "__main__":
    parser = argparse.ArgumentParser(description="Run test of model on mbpp dataset")
    parser.add_argument("--indir", type=str, help="statistic file", default="datasets/mbpp")
    parser.add_argument("--outdir", type=str, help="", default="temp")
    parser.add_argument("--gguf_model", type=str, help="path to model in gguf format", default=None)
    parser.add_argument("--llama_random_seed", type=int, help="", default=2)
    parser.add_argument("--llama_threads", type=int, help="", default=8)
    parser.add_argument("--llama_n_ctx", type=int, help="", default=2048)
    parser.add_argument("--llama_max_tokens", type=int, help="", default=200)
    parser.add_argument("--llama_stop", type=str, help="", default="<|end|>")
    parser.add_argument("--llama_echo", type=bool, help="", default=False)
    parser.add_argument("--llama_temperature", type=float, help="", default=0.5)
    parser.add_argument("--llama_top_k", type=int, help="", default=None)
    parser.add_argument("--llama_top_p", type=float, help="", default=None)



    parser.add_argument("--verbose", type=int, help="Verbose level", default=1)
    args = parser.parse_args()
    indir = args.indir
    outdir = args.outdir
    gguf_model = args.gguf_model
    verbose = args.verbose
    #create output directory

    model_do_not_defined = True
    gguf_model_flag = False
    model_name=""
    if gguf_model is not None:
        model_do_not_defined = False
        gguf_model_flag = True
        filename = os.path.abspath(gguf_model)
        model_name = os.path.basename(gguf_model).split(".")[0]
    if model_do_not_defined:
        raise RuntimeError("Model is not defined")

    if not os.path.exists(outdir):
        os.makedirs(outdir)
        # create subdir in outdir with name of model and current date
    outdir = os.path.join(outdir, model_name)
    if not os.path.exists(outdir):
        os.makedirs(outdir)

    #get list of *.py files from indir
    py_files = [f for f in os.listdir(indir) if f.endswith('.py')]

    model_kwargs = {
        "seed": args.llama_random_seed,
        "n_threads": args.llama_threads,
        "n_ctx": args.llama_n_ctx
    }

    #initialize model
    if gguf_model_flag:
        llm = Llama(model_path=filename, **model_kwargs,verbose=(verbose>1))
    else:
        raise RuntimeError("Not implemented yet")

    generation_kwargs = {}
    if args.llama_max_tokens is not None:
        generation_kwargs["max_tokens"] = args.llama_max_tokens
    if args.llama_stop is not None:
        generation_kwargs["stop"] = [args.llama_stop]
    if args.llama_echo is not None:
        generation_kwargs["echo"] = args.llama_echo
    if args.llama_temperature is not None:
        generation_kwargs["temperature"] = args.llama_temperature
    if args.llama_top_k is not None:
        generation_kwargs["top_k"] = args.llama_top_k
    if args.llama_top_p is not None:
        generation_kwargs["top_p"] = args.llama_top_p

    i = 0
    for py_file in tqdm.tqdm(py_files,desc='Run tests on mbpp dataset',disable=verbose!=1):
        prompt,tests = construct_prompt(os.path.join(indir,py_file))
        res = llm(prompt, **generation_kwargs)  # Perform inference
        generated_text = res["choices"][0]["text"]
        if verbose > 2:
            print(f"prompt:\n{prompt}")
            print(f"Inference output:\n{generated_text}\n")
        output_str = prompt + generated_text
        #remove all lines after if __name__ == "__main__":
        lines = output_str.split("\n")
        output_str = ""
        for l in lines:
            if "__name__" in l:
                break
            output_str += l + "\n"
        output_str += tests
        out_file = f"{py_file.split('.')[0]}"
        if "temperature" in generation_kwargs:
            out_file += f"_t{generation_kwargs['temperature']}"
        if args.llama_random_seed is not None:
            out_file += f"_s{args.llama_random_seed}"
        if "top_k" in generation_kwargs:
            out_file += f"_k{generation_kwargs['top_k']}"
        if "top_p" in generation_kwargs:
            out_file += f"_p{generation_kwargs['top_p']}"
        out_file += ".py"
        with open(os.path.join(outdir,out_file), "w") as f:
            f.write(output_str)
