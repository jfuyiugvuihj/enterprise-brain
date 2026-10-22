import os
os.environ['HF_ENDPOINT'] = 'https://hf-mirror.com'
from sentence_transformers import CrossEncoder
print('Downloading BAAI/bge-reranker-base from hf-mirror.com...')
m = CrossEncoder('BAAI/bge-reranker-base')
print('Download complete!')
