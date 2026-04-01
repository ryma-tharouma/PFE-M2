from pydantic import BaseModel


class QAPair(BaseModel):
    """
    Represents a Question-Answer pair for the FAQ index.
    """

    id: str                      # unique identifier
    app: str                     # application name (same as Section.app)

    question: str                # user-facing question
    answer: str                  # short, direct answer

    source_section_id: str       # link back to original section

    confidence: float = 1.0      # optional score (useful later for filtering)