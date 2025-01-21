import re
import os
import tqdm
import inspect
import argparse
import pandas as pd
from matplotlib import pyplot as plt


if __name__ == "__main__":

    parser = argparse.ArgumentParser(
        description="test_analysis.py - tool for analysis of test scripts",
        formatter_class=argparse.RawTextHelpFormatter)
    parser.add_argument("-testfile", help="File with test script", type=str,
                        required=True)
    parser.add_argument("-outfile", help="Results of analysis", type=str,
                        default="")
    args = parser.parse_args()
    testfile = args.testfile
    outfile = args.outfile

    #read csv file to Dataframe
    df = pd.read_csv(testfile)
    #compute number of True in column results for each value of column 't'
    tests_from_t = []
    success_from_t = []
    total_number_of_unique_tests = len(df['test_id'].unique())
    for t in df['t'].unique():
        success_from_t.append({"t": t, "True": len(df[(df['t'] == t) & (df['result'] == True)])/len(df[df['t'] == t])})
        #with fixed t number of unique values of 'test_id' with True result
        tmp_df = df[(df['t'] == t) & (df['result'] == True)]
        tests_from_t.append({"t": t, "True": len(tmp_df['test_id'].unique())/total_number_of_unique_tests})
    temp_sort = sorted(df['t'].unique().tolist())
    comulative_success = []
    success_test_id = []
    for t in temp_sort:
        for s in df['s'].unique():
            tmp_df = df[(df['t'] == t) & (df['result'] == True) & (df['s'] == s)]
            test_ids = tmp_df['test_id'].unique().tolist()
            success_test_id+=test_ids
            success_test_id = list(set(success_test_id))
            print(f"{t} {s} {len(success_test_id)/total_number_of_unique_tests} {len(test_ids)}")
            comulative_success.append({"t": t+s/100, "True": len(success_test_id)/total_number_of_unique_tests})
    #sort by t
    success_from_t = sorted(success_from_t, key=lambda x: x['t'])
    tests_from_t = sorted(tests_from_t, key=lambda x: x['t'])
    fig,axes = plt.subplots(3)
    axes[0].plot([x['t'] for x in success_from_t], [x['True'] for x in success_from_t])
    axes[0].set_title("Number of correct results to all attempts from temperature")
    axes[0].set_xlabel("t")
    axes[0].set_ylabel("Number of correct results to all attempts")
    #bar plot of number of success tests to all tests from temperature
    axes[1].bar([x['t'] for x in tests_from_t], [x['True'] for x in tests_from_t], width=0.05)
    axes[1].set_title("Number of success tests to all tests from temperature")
    axes[1].set_xlabel("t")
    axes[1].set_ylabel("Number of success tests to all tests")
    #plot of comulative success
    axes[2].plot([x['t'] for x in comulative_success], [x['True'] for x in comulative_success])
    axes[2].set_title("Comulative success")
    axes[2].set_xlabel("t")
    axes[2].set_ylabel("Comulative success")
    plt.tight_layout()


    if outfile != "":
        plt.savefig(outfile)
    else:
        plt.show()
