'''
This script processes a directory containing Python files generated for the MBPP-56 test, validating their code and functionality.
It parses filenames to extract metadata (test ID, model parameters), attempts to fix and load faulty code,
and runs the `test_check` function within each file to verify results. Outputs a CSV summary of validation outcomes.
'''
import re
import os
import tqdm
import inspect
import argparse
import pandas as pd

import builtins

# Save the original input function
original_input = builtins.input

# Define a mock input function to do not stop execution
def mock_input(prompt=""):
    return "42"

# Replace the input function with the mock
builtins.input = mock_input
def parse_filename(filename):
    """
    Parse a filename of the form:
        <test_id>_t<float>_s<int>_k<int>_p<float>.py
    where each of t, s, k, and p parts are optional. The '.py' extension
    is always present, and <test_id> is one or more underscores/tokens
    before the optional t/s/k/p parts.

    Args:
        filename (str): The input filename (e.g., "mbpp_56_checks_t0.2_s2_k50_p0.9.py").

    Returns:
        tuple:
            (test_id (str),
             t (float or None),
             s (int or None),
             k (int or None),
             p (float or None))
    """
    # 1. Remove the .py extension if present
    if filename.endswith(".py"):
        filename = filename[:-3]  # Strip off ".py"
    else:
        raise ValueError("Filename must end with '.py'")

    # 2. Split the filename by underscores
    parts = filename.split("_")

    # Initialize the results to None
    t_val = None
    s_val = None
    k_val = None
    p_val = None

    # Regex patterns to detect t, s, k, p tokens
    t_pattern = re.compile(r"^t(\d+(\.\d+)?)$")
    s_pattern = re.compile(r"^s(\d+)$")
    k_pattern = re.compile(r"^k(\d+)$")
    p_pattern = re.compile(r"^p(\d+(\.\d+)?)$")

    # We'll collect parts of test_id here
    test_id_parts = []

    # 3. Iterate through each part and classify
    for part in parts:
        t_match = t_pattern.match(part)
        s_match = s_pattern.match(part)
        k_match = k_pattern.match(part)
        p_match = p_pattern.match(part)

        if t_match:
            # Capture the float value for t
            t_val = float(t_match.group(1))
        elif s_match:
            # Capture the integer value for s
            s_val = int(s_match.group(1))
        elif k_match:
            # Capture the integer value for k
            k_val = int(k_match.group(1))
        elif p_match:
            # Capture the float value for p
            p_val = float(p_match.group(1))
        else:
            # If none of the patterns matched, it's part of test_id
            test_id_parts.append(part)

    # 4. Reconstruct test_id by joining leftover parts
    test_id = "_".join(test_id_parts)

    # 5. Return all desired values
    return test_id, t_val, s_val, k_val, p_val

def load_valid_functions_with_recovery(file_path):
    """
    Load all valid functions from a Python file, ignoring syntax errors in broken code blocks.
    """
    namespace = {}
    valid_functions = {}

    #read all lines from file:
    with open(file_path, "r") as f:
        lines = f.readlines()

    #lines_fix = fix_python_code("".join(lines))
    #split lines by \n
    lines_fix = "".join(lines)
    lines_fix = lines_fix.split("\n")
    correct_functions=[]
    current_block = ""
    i = 0
    while i < len(lines_fix):
        line = lines_fix[i]
        current_block += line + '\n'
        if line.strip().startswith("def "):
            if line.strip().endswith(":"):
               k = 0
               while i < len(lines_fix)-1 and ('def' not in lines_fix[i+1]):
                    i += 1
                    line = lines_fix[i]
                    #Is line contain only whitespaces?
                    if len(line.strip())>0:
                        current_block += line + '\n'
                        k += 1
               if k == 0:
                   current_block += "\tpass\n"
        try:
            # Attempt to execute the accumulated block of code
            exec(current_block, namespace)
        except SyntaxError as e:
            #print(f"Syntax error encountered: {e}")
            #print(current_block)
            #print(i)
            # Continue accumulating lines until the broken block ends
            current_block = ""  # Clear the block after successful execution
            i=i+1
            continue
        except Exception as e:
            # Catch and log any runtime exceptions without halting the execution
            #print(f"Runtime error encountered: {e}")
            current_block = ""  # Clear the block after successful execution
            i = i + 1
            continue
        correct_functions.append(current_block)
        current_block = ""
        i = i + 1
    # Filter valid functions from the namespace
    for name, obj in namespace.items():
        if inspect.isfunction(obj):
            valid_functions[name] = obj

    return valid_functions

import multiprocessing
import contextlib
import os
import sys

def run_target_function(target_func, function_list):
    """
    Runs the target function (target_func) in a separate process while:
    1) Suppressing stdout and stderr.
    2) Enforcing a 5-second time limit.
    3) Propagating any exceptions raised by target_func.

    :param target_func: The function to run in a separate process.
    :param function_list: List of function objects that target_func may use.
    :return: The return value of target_func, if any.
    :raises RuntimeError: If the execution exceeds 5 seconds.
    :raises Exception: Re-raises any exception from the target function.
    """

    # We'll use a multiprocessing.Queue to communicate results (or exceptions).
    result_queue = multiprocessing.Queue()

    def _worker():
        # Suppress stdout and stderr in the child process
        with open(os.devnull, 'w') as devnull:
            with contextlib.redirect_stdout(devnull), contextlib.redirect_stderr(devnull):
                try:
                    # Call the target function (pass the function_list if needed)
                    result = target_func()
                    # Indicate success and send result back
                    result_queue.put(('success', result))
                except Exception as ex:
                    # Indicate exception and send exception back
                    result_queue.put(('exception', ex))

    # Create a separate process that runs our worker
    process = multiprocessing.Process(target=_worker)
    process.start()
    # Wait for up to 5 seconds
    process.join(timeout=2)

    # If still alive after 5 seconds, kill the child process and raise an error
    if process.is_alive():
        process.kill()
        process.join()
        raise RuntimeError("Too long execution")

    # Fetch results from the queue (if any)
    if not result_queue.empty():
        status, payload = result_queue.get()
        if status == 'success':
            return payload
        else:  # status == 'exception'
            # Re-raise the exception that occurred in the child process
            raise payload

    # In principle, we shouldn't get here without a result,
    # but just in case, return None or raise an error
    return None

if __name__ == "__main__":
    multiprocessing.set_start_method("fork")
    parser = argparse.ArgumentParser(description="Check results of mbpp_56 test. Open each file, check syntax and run test_check function")
    parser.add_argument("--indir", type=str, help="Directory with results of run of LLM. Expected one file - one task.", required=True)
    parser.add_argument("--outfile", type=str, help="", required=True)
    parser.add_argument("--verbose", type=int, help="Verbose level", default=1)

    args = parser.parse_args()

    directory_with_mbpp_testfiles = args.indir
    outfile = args.outfile
    verbose = args.verbose
    #obtain a list of python files in the directory
    files = [f for f in os.listdir(directory_with_mbpp_testfiles) if f.endswith('.py')]

    test_results = []
    fn = 0
    for f in tqdm.tqdm(files,disable=verbose!=1):
        if verbose > 1:
            fn +=1
            print(f"Processing file: {f} ({fn}/{len(files)})")
        res = {}
        full_path = os.path.join(directory_with_mbpp_testfiles, f)
        res["filename"] = os.path.basename(full_path)
        # Load valid functions
        if verbose > 2:
            print(f"Loading functions from file: {full_path}")
        functions = load_valid_functions_with_recovery(full_path)

        # Print loaded functions
        for name, func in functions.items():
            if verbose > 2:
                print(f"Loaded function: {name}")

        # Example: Call the `test_check` function to validate the `pair_wise` implementation
        res["error"] = None
        if "test_check" in functions:
            test_check = functions["test_check"]
            if verbose > 2:
                print("Running test_check...")
            try:
                # Call the test_check function and suppress any output
                result = run_target_function(test_check, functions)

                if verbose > 2:
                    print("All tests passed!")
            except AssertionError as e:
                if verbose > 2:
                    print(f"Assertion error encountered: {e}")
                res["error"] = f"Assertion error encountered: {e}"
            except Exception as e:
                if verbose > 2:
                    print(f"Error encountered: {e}")
                res["error"] = f"Error encountered: {e}"
        else:
            if verbose > 2:
                print("No test_check function found.")
            res["error"] = "No test_check function found."
        res["result"] = res["error"] is None
        test_id, t_val, s_val, k_val, p_val = parse_filename(f)
        res["test_id"] = test_id
        res["t"] = t_val
        res["s"] = s_val
        res["k"] = k_val
        res["p"] = p_val
        test_results.append(res)
        #unload functions
        for func in functions:
            del func
    df = pd.DataFrame(test_results)
    df.to_csv(outfile,index=False)
