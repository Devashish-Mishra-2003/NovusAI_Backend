from pydantic import BaseModel


class AuthUser(BaseModel):
    user_id: int
    email: str
    name: str
    role: str          # ADMIN | EMPLOYEE
    company_id: int
    company_name: str
