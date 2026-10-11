"""Optional manual tool smoke test; no paid API calls."""
import sys
from pathlib import Path
if __package__ in {None, ''}:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from server.tools.executor import execute_tool


def main():
    result = execute_tool('grade_calculator', {'components': [
        {'name': 'Exam', 'grade': 82, 'weight': 70},
        {'name': 'Project', 'grade': 95, 'weight': 30},
    ]})
    assert result['final_grade'] == 85.9
    print('Grade Calculator:', result)
    print('Course lookup:', execute_tool('course_information_lookup', {'query': 'Final Project'}))


if __name__ == '__main__':
    main()
