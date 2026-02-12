import pandas as pd
from database.session import SessionLocal
from database.models import Contract, ProjectSlots
from datetime import datetime

def process_excel_file(file_path, project_name=None, address_ru=None, address_uz=None, slots_limit=None, latitude=None, longitude=None):
    """
    Импорт контрактов из Excel.
    
    Args:
        file_path: путь к Excel файлу
        project_name: название проекта (если None, берется из первой строки)
        address_ru: адрес проекта на русском (для создания/обновления ProjectSlots)
        address_uz: адрес проекта на узбекском (для создания/обновления ProjectSlots)
        slots_limit: лимит слотов для проекта (для создания/обновления ProjectSlots)
        latitude: широта геолокации проекта
        longitude: долгота геолокации проекта
    
    Returns:
        tuple: (количество импортированных контрактов, название проекта)
    """
    # Указываем формат даты, если он специфический, или полагаемся на автоопределение
    df = pd.read_excel(file_path)
    df.columns = [c.strip() for c in df.columns]

    count = 0
    detected_project = None
    
    with SessionLocal() as session:
        for _, row in df.iterrows():
            clean_contract = "".join(str(row['Номер договора']).split()).upper()

            # Преобразование даты сдачи
            raw_delivery_date = row['Дата сдачи']
            if isinstance(raw_delivery_date, str):
                delivery_date = datetime.strptime(raw_delivery_date, '%d.%m.%Y').date()
            else:
                delivery_date = raw_delivery_date.date()

            house_name = str(row['Название дома'])
            
            # Определяем название проекта
            if detected_project is None:
                detected_project = house_name
            
            # Если указан конкретный project_name, проверяем соответствие
            if project_name and house_name != project_name:
                continue  # Пропускаем контракты не из этого проекта

            contract = session.query(Contract).filter_by(contract_num=clean_contract).first()

            data = {
                "house_name": house_name,
                "apt_num": str(row['Номер квартиры']),
                "entrance": str(row['Подьезд']),
                "floor": int(row['Этаж']),
                "contract_num": clean_contract,
                "client_fio": str(row['ФИО клиента']),
                "delivery_date": delivery_date
            }

            if contract:
                for key, value in data.items(): 
                    setattr(contract, key, value)
            else:
                session.add(Contract(**data))
            count += 1
        
        # Создаем или обновляем ProjectSlots если переданы параметры
        if (address_ru or address_uz or slots_limit or latitude or longitude) and detected_project:
            project_slot = session.query(ProjectSlots).filter_by(project_name=detected_project).first()
            
            if project_slot:
                # Обновляем существующий
                if address_ru:
                    project_slot.address_ru = address_ru
                if address_uz:
                    project_slot.address_uz = address_uz
                if slots_limit is not None:
                    project_slot.slots_limit = slots_limit
                if latitude:
                    project_slot.latitude = latitude
                if longitude:
                    project_slot.longitude = longitude
            else:
                # Создаем новый
                session.add(ProjectSlots(
                    project_name=detected_project,
                    address_ru=address_ru,
                    address_uz=address_uz,
                    slots_limit=slots_limit if slots_limit is not None else 1,
                    latitude=latitude,
                    longitude=longitude
                ))
        
        session.commit()
    
    return count, detected_project