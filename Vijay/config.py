from pydantic import BaseModel, Field
class Embedconfig(BaseModel):
    collection_name: str= "pdf_ppt_xl.pdf"
    vector_size : int=Field(default=364,gt=0)
    batch_size : int=(Field(default=32, gt=0))
    chunk_size : int=(Field(default=1000, gt=0))
    chunk_overlap :int=(Field(default=200, gt=0))
config=Embedconfig()
collection_name="pdf_ppt_xl"