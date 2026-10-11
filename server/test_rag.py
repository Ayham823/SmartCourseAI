"""Manual retrieval demo, safely excluded from pytest's tests/ discovery."""
import argparse
import sys
from pathlib import Path
if __package__ in {None, ''}:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from server.rag.retriever import retrieve_chunks


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('question', nargs='?', default='How do I authenticate with the Anthropic Python SDK?')
    query = parser.parse_args().question
    for result in retrieve_chunks(query, limit=5):
        print(f"{result['source']} | page {result['page_number']} | similarity {result['similarity']:.4f}")
        print(result['content'][:700])


if __name__ == '__main__':
    main()
