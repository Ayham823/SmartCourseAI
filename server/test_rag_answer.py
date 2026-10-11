"""Optional live RAG generation demo; consumes Anthropic API credits."""
import argparse
import sys
from pathlib import Path
if __package__ in {None, ''}:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from server.errors import AppError
from server.rag.service import answer_question


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('question', nargs='?', default='How do I authenticate with the Anthropic Python SDK?')
    try:
        result = answer_question(parser.parse_args().question)
    except AppError as error:
        print(error.message)
        raise SystemExit(1)
    print(result['answer'])
    print('Sources:', result['sources'])


if __name__ == '__main__':
    main()
