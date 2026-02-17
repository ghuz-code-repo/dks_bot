from aiogram.fsm.state import StatesGroup, State

class ClientSteps(StatesGroup):
    # Основной флоу добавления записи
    entering_contract = State()
    selecting_date = State()
    selecting_time = State()
    entering_phone = State()
    
    # Флоу отмены записи
    cancel_selecting_booking = State()
    cancel_confirming = State()
    
    # Флоу перезаписи
    calendar_selecting_booking = State()
    calendar_viewing = State()
    calendar_selecting_time = State()
    calendar_rebook_confirming = State()
    calendar_entering_phone = State()


class AdminSteps(StatesGroup):
    """Состояния для работы админ-панели"""
    # Управление персоналом
    waiting_for_admin_id = State()
    waiting_for_employee_id = State()
    waiting_for_staff_id_to_delete = State()
    
    # Управление слотами
    selecting_project_for_slots = State()
    waiting_for_slot_limit = State()
    
    # Управление адресами проектов
    selecting_project_for_address = State()
    waiting_for_address_ru = State()
    waiting_for_address_uz = State()
    
    # Добавление нового проекта
    add_project_address_ru = State()
    add_project_address_uz = State()
    add_project_slots_limit = State()
    add_project_latitude = State()
    add_project_longitude = State()
    add_project_excel = State()
    
    # Просмотр записей по проекту
    selecting_project_for_bookings = State()
    selecting_weeks_for_bookings = State()
    selecting_day_for_bookings = State()

    # Редактирование настроек проекта
    edit_project_select = State()
    edit_project_action = State()
    edit_project_address_ru = State()
    edit_project_address_uz = State()
    edit_project_latitude = State()
    edit_project_longitude = State()

    # Изменение списка договоров
    update_contracts_selecting_project = State()
    update_contracts_waiting_excel = State()
    update_contracts_confirming = State()


class EmployeeSteps(StatesGroup):
    """Состояния для работы панели сотрудника"""
    selecting_project_for_bookings = State()
    selecting_weeks_for_bookings = State()
    selecting_day_for_bookings = State()
