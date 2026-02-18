import logging
import pandas as pd
from database.session import SessionLocal
from database.models import Contract, ProjectSlots
from datetime import datetime

# Ожидаемые названия столбцов в правильном порядке
EXPECTED_COLUMNS = [
    'Название дома',
    'Номер квартиры',
    'Подъезд',
    'Этаж',
    'Номер договора',
    'ФИО клиента',
    'Дата сдачи',
]


def _detect_columns(df):
    """
    Определяет маппинг столбцов.

    1) Если все ожидаемые заголовки присутствуют — используем их по именам.
    2) Иначе — считаем, что столбцы расположены позиционно в порядке EXPECTED_COLUMNS.

    Returns:
        dict: маппинг логическое_имя -> реальное имя столбца в DataFrame
    """
    stripped = [c.strip() for c in df.columns]
    df.columns = stripped

    missing = [col for col in EXPECTED_COLUMNS if col not in stripped]

    if not missing:
        # Все заголовки найдены — используем по именам
        logging.info("Excel: все ожидаемые заголовки найдены, используем по именам.")
        return {col: col for col in EXPECTED_COLUMNS}, df

    # Фолбэк: позиционный доступ
    if len(df.columns) < len(EXPECTED_COLUMNS):
        raise ValueError(
            f"В файле {len(df.columns)} столбцов, ожидается минимум {len(EXPECTED_COLUMNS)}. "
            f"Ожидаемый порядок: {', '.join(EXPECTED_COLUMNS)}"
        )

    logging.info(
        "Excel: заголовки не совпадают (отсутствуют: %s). Используем позиционный порядок столбцов.",
        ', '.join(missing),
    )
    mapping = {}
    for idx, expected_name in enumerate(EXPECTED_COLUMNS):
        mapping[expected_name] = df.columns[idx]
    return mapping, df


def process_excel_file(file_path, project_name=None, address_ru=None, address_uz=None, slots_limit=None, latitude=None, longitude=None):
    """
    Импорт контрактов из Excel.
    
    Логика определения столбцов:
      1) Если заголовки в файле совпадают с ожидаемыми — данные читаются по именам столбцов.
      2) Если хотя бы один заголовок не совпадает — данные читаются позиционно,
         в порядке: Название дома, Номер квартиры, Подъезд, Этаж, Номер договора,
         ФИО клиента, Дата сдачи.
    
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
    df = pd.read_excel(file_path)
    col_map, df = _detect_columns(df)

    count = 0
    detected_project = None
    
    with SessionLocal() as session:
        for _, row in df.iterrows():
            clean_contract = "".join(str(row[col_map['Номер договора']]).split()).upper()

            # Преобразование даты сдачи
            raw_delivery_date = row[col_map['Дата сдачи']]
            if isinstance(raw_delivery_date, str):
                delivery_date = datetime.strptime(raw_delivery_date, '%d.%m.%Y').date()
            else:
                delivery_date = raw_delivery_date.date()

            house_name = str(row[col_map['Название дома']])
            
            # Определяем название проекта
            if detected_project is None:
                detected_project = house_name
            
            # Если указан конкретный project_name, проверяем соответствие
            if project_name and house_name != project_name:
                continue  # Пропускаем контракты не из этого проекта

            contract = session.query(Contract).filter_by(contract_num=clean_contract).first()

            data = {
                "house_name": house_name,
                "apt_num": str(row[col_map['Номер квартиры']]),
                "entrance": str(row[col_map['Подъезд']]),
                "floor": int(row[col_map['Этаж']]),
                "contract_num": clean_contract,
                "client_fio": str(row[col_map['ФИО клиента']]),
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


def analyze_excel_changes(file_path, project_name):
    """
    Анализ Excel-файла и сравнение с текущими данными в БД.
    
    Сопоставление по house_name + apt_num.
    
    Returns:
        dict с ключами:
            - new_contracts: список новых квартир (не найдены в БД)
            - updated_contracts: список квартир с изменёнными данными (без смены договора)
            - changed_contracts: список квартир со сменой номера договора
    """
    from database.models import Booking

    df = pd.read_excel(file_path)
    col_map, df = _detect_columns(df)

    new_contracts = []
    updated_contracts = []
    changed_contracts = []

    with SessionLocal() as session:
        for _, row in df.iterrows():
            house_name = str(row[col_map['Название дома']])

            if house_name != project_name:
                continue

            apt_num = str(row[col_map['Номер квартиры']])
            clean_contract = "".join(str(row[col_map['Номер договора']]).split()).upper()

            raw_delivery_date = row[col_map['Дата сдачи']]
            if isinstance(raw_delivery_date, str):
                delivery_date = datetime.strptime(raw_delivery_date, '%d.%m.%Y').date()
            else:
                delivery_date = raw_delivery_date.date()

            new_data = {
                "house_name": house_name,
                "apt_num": apt_num,
                "entrance": str(row[col_map['Подъезд']]),
                "floor": int(row[col_map['Этаж']]),
                "contract_num": clean_contract,
                "client_fio": str(row[col_map['ФИО клиента']]),
                "delivery_date": delivery_date.isoformat(),
            }

            # Ищем существующий контракт по дому + квартире
            existing = session.query(Contract).filter_by(
                house_name=house_name, apt_num=apt_num
            ).first()

            if not existing:
                # Новая квартира
                new_contracts.append(new_data)
            elif existing.contract_num != clean_contract:
                # Изменился номер договора
                active_bookings = session.query(Booking).filter(
                    Booking.contract_id == existing.id,
                    Booking.is_cancelled == False
                ).count()
                changed_contracts.append({
                    "contract_id": existing.id,
                    "apt_num": apt_num,
                    "old_contract_num": existing.contract_num,
                    "new_contract_num": clean_contract,
                    "active_bookings_count": active_bookings,
                    "telegram_id": existing.telegram_id,
                    "new_data": new_data,
                })
            else:
                # Проверяем изменения в остальных полях
                changes = {}
                if existing.entrance != new_data["entrance"]:
                    changes["entrance"] = {"old": existing.entrance, "new": new_data["entrance"]}
                if existing.floor != new_data["floor"]:
                    changes["floor"] = {"old": existing.floor, "new": new_data["floor"]}
                if existing.client_fio != new_data["client_fio"]:
                    changes["client_fio"] = {"old": existing.client_fio, "new": new_data["client_fio"]}

                existing_dd = existing.delivery_date.isoformat() if existing.delivery_date else None
                if existing_dd != new_data["delivery_date"]:
                    changes["delivery_date"] = {"old": existing_dd, "new": new_data["delivery_date"]}

                if changes:
                    updated_contracts.append({
                        "contract_id": existing.id,
                        "apt_num": apt_num,
                        "contract_num": existing.contract_num,
                        "changes": changes,
                    })

    return {
        "new_contracts": new_contracts,
        "updated_contracts": updated_contracts,
        "changed_contracts": changed_contracts,
    }


def apply_contract_changes(new_contracts=None, minor_updates=None, review_decisions=None):
    """
    Применение изменений в БД.
    
    Args:
        new_contracts: список данных для новых квартир (добавить)
        minor_updates: список {contract_id, changes} для обновления полей (без ФИО)
        review_decisions: список индивидуальных решений по договорам:
            Каждый элемент содержит:
            - type: "fio_change" или "contract_change"
            - contract_id: ID контракта
            - actions: set из выбранных действий: {"unbind_tg", "cancel_bookings", "notify"}
            - changes / new_data: данные для обновления
    
    Returns:
        dict с результатами:
            - added: количество добавленных
            - updated: количество обновлённых
            - contracts_changed: количество изменённых договоров
            - bookings_cancelled: количество аннулированных записей
            - unbound_tg: количество отвязанных аккаунтов
            - notifications: список telegram_id для отправки уведомлений
    """
    from database.models import Booking

    result = {
        "added": 0,
        "updated": 0,
        "contracts_changed": 0,
        "bookings_cancelled": 0,
        "unbound_tg": 0,
        "notifications": [],
    }

    with SessionLocal() as session:
        # 1. Добавление новых квартир
        if new_contracts:
            for item in new_contracts:
                data = dict(item)
                data["delivery_date"] = datetime.fromisoformat(data["delivery_date"]).date()
                session.add(Contract(**data))
                result["added"] += 1

        # 2. Применение незначительных обновлений (без ФИО)
        if minor_updates:
            for item in minor_updates:
                contract = session.query(Contract).get(item["contract_id"])
                if contract:
                    for key, change in item["changes"].items():
                        value = change["new"]
                        if key == "delivery_date":
                            value = datetime.fromisoformat(value).date()
                        setattr(contract, key, value)
                    result["updated"] += 1

        # 3. Применение индивидуальных решений по договорам
        if review_decisions:
            for item in review_decisions:
                actions = set(item.get("actions", []))

                contract = session.query(Contract).get(item["contract_id"])
                if not contract:
                    continue

                # Уведомление — сохраняем telegram_id ДО возможной отвязки
                if "notify" in actions and contract.telegram_id:
                    result["notifications"].append(contract.telegram_id)

                # Аннулировать активные записи
                if "cancel_bookings" in actions:
                    active_bookings = session.query(Booking).filter(
                        Booking.contract_id == contract.id,
                        Booking.is_cancelled == False
                    ).all()
                    for booking in active_bookings:
                        booking.is_cancelled = True
                        result["bookings_cancelled"] += 1

                # Отвязать telegram
                if "unbind_tg" in actions:
                    if contract.telegram_id:
                        contract.telegram_id = None
                        result["unbound_tg"] += 1

                # Всегда обновляем данные контракта
                if item["type"] == "contract_change":
                    new_data = item["new_data"]
                    contract.contract_num = new_data["contract_num"]
                    contract.entrance = new_data["entrance"]
                    contract.floor = new_data["floor"]
                    contract.client_fio = new_data["client_fio"]
                    contract.delivery_date = datetime.fromisoformat(new_data["delivery_date"]).date()
                    result["contracts_changed"] += 1
                elif item["type"] == "fio_change":
                    for key, change in item["changes"].items():
                        value = change["new"]
                        if key == "delivery_date":
                            value = datetime.fromisoformat(value).date()
                        setattr(contract, key, value)
                    result["updated"] += 1

        session.commit()

    return result