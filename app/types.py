from pydantic import BaseModel
from typing import List, Optional, Any, Dict, Union

class FinancialDocument(BaseModel):
    pre_text: Optional[List[str]]
    post_text: Optional[List[str]]
    filename: Optional[str]
    table: Optional[List[List[str]]]
    table_ori: Optional[List[List[str]]]
    id: Optional[str]
    annotation: Optional[Dict[str, Any]]

    class Config:
        extra = 'ignore'
