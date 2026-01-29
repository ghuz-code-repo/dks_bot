import pandas as pd
from database.session import SessionLocal
from database.models import Contract
from datetime import datetime

def process_excel_file(file_path):
    # Указываем формат даты, если он специфический, или полагаемся на автоопределение
    df = pd.read_excel(file_path)
    df.columns = [c.strip() for c in df.columns]

    count = 0
    with SessionLocal() as session:
        for _, row in df.iterrows():
            clean_contract = "".join(str(row['Номер договора']).split()).upper()

            # Преобразование даты сдачи
            raw_delivery_date = row['Дата сдачи']
            if isinstance(raw_delivery_date, str):
                delivery_date = datetime.strptime(raw_delivery_date, '%d.%m.%Y').date()
            else:
                delivery_date = raw_delivery_date.date()

            contract = session.query(Contract).filter_by(contract_num=clean_contract).first()

            data = {
                "house_name": str(row['Название дома']),
                "apt_num": str(row['Номер квартиры']),
                "entrance": str(row['Подьезд']),
                "floor": int(row['Этаж']),
                "contract_num": clean_contract,
                "client_fio": str(row['ФИО клиента']),
                "delivery_date": delivery_date
            }

            if contract:
                for key, value in data.items(): setattr(contract, key, value)
            else:
                session.add(Contract(**data))
            count += 1
        session.commit()
    return count