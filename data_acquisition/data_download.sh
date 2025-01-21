#!/bin/bash
wget https://github.com/snakemake/snakemake-workflow-catalog/blob/95e91278f86e8de9ee3201935f1f6ea5e2a2d2e6/data.js
python train_data_web_crawler.py  -data_file data.js -output_dir standart_pipelines_best --stars_min 5 --standart
python train_data_web_crawler.py  -data_file data.js -output_dir standart_pipelines --stars_min 0 --standart
python train_data_web_crawler.py  -data_file data.js -output_dir all_pipelines_best --stars_min 10
python train_data_web_crawler.py  -data_file data.js -output_dir all_pipelines --stars_min 2 --partial

