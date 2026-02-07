from app.db.session import SessionLocal
from app.models.notice import ProcurementNotice

db = SessionLocal()

# Notices avec "construction"
construction = db.query(ProcurementNotice).filter(
    (ProcurementNotice.title.ilike('%construction%')) | 
    (ProcurementNotice.description.ilike('%construction%'))
).count()

# Notices avec CPV 45000000
cpv_45 = db.query(ProcurementNotice).filter(
    ProcurementNotice.cpv_main_code.like('45000000%')
).count()

# Notices avec "travaux"
travaux = db.query(ProcurementNotice).filter(
    (ProcurementNotice.title.ilike('%travaux%')) | 
    (ProcurementNotice.description.ilike('%travaux%'))
).count()

print(f'Total notices in DB: {db.query(ProcurementNotice).count()}')
print(f'Notices with construction: {construction}')
print(f'Notices with travaux: {travaux}')
print(f'Notices with CPV 45000000: {cpv_45}')

db.close()
