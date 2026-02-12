from aiogram.fsm.state import StatesGroup, State

class ClientSteps(StatesGroup):
    selecting_house = State()
    entering_contract = State()
    selecting_date = State()
    selecting_time = State()
    entering_phone = State()


class AdminSteps(StatesGroup):
    """Состояния для работы админ-панели"""
    # Управление персоналом
    waiting_for_admin_id = State()
    waiting_for_employee_id = State()
    waiting_for_staff_id_to_delete = State()
    
    # Управление слотами
    selecting_project_for_slots = State()
    waiting_for_slot_limit = State()
