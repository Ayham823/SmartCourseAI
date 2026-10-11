TOOLS = [
    {
        "name": "grade_calculator",
        "description": (
            "Calculate a student's final course grade "
            "from grades and percentage weights."
        ),
        "input_schema": {
            "type": "object",
            "additionalProperties": False,
            "properties": {
                "components": {
                    "type": "array",
                    "minItems": 1,
                    "maxItems": 30,
                    "description": (
                        "List of graded course components."
                    ),
                    "items": {
                        "type": "object",
                        "additionalProperties": False,
                        "properties": {
                            "name": {
                                "type": "string", "minLength": 1, "maxLength": 120
                            },
                            "grade": {
                                "type": "number", "minimum": 0, "maximum": 100
                            },
                            "weight": {
                                "type": "number", "minimum": 0, "maximum": 100
                            }
                        },
                        "required": [
                            "name",
                            "grade",
                            "weight"
                        ]
                    }
                }
            },
            "required": ["components"]
        }
    },

    {
        "name": "course_information_lookup",
        "description": (
            "Look up structured course information such as "
            "assignment deadlines, exam dates and weights."
        ),
        "input_schema": {
            "type": "object",
            "additionalProperties": False,
            "properties": {
                "query": {
                    "type": "string",
                    "minLength": 1,
                    "maxLength": 2000,
                    "description": (
                        "Course item to search for, for example "
                        "'Final Project' or 'Final Exam'."
                    )
                }
            },
            "required": ["query"]
        }
    }
]
