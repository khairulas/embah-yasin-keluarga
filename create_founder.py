# create_founder.py  (one-off; delete after)
import os
from dotenv import load_dotenv
load_dotenv()

from app.repositories import PersonRepository

repo = PersonRepository()
pid = repo.create(
    {"full_name": "Embah Yasin", "jantina": "L", "status": "deceased"},
    actor={"uid": "system", "email": "system@embahyasin", "name": "Founder seed"},
    person_id="p_embah-yasin",
)
print("Created:", pid)