from aiogram.fsm.state import StatesGroup, State

class ClientSteps(StatesGroup):
    selecting_house = State()
    entering_contract = State()
    selecting_date = State()
    selecting_time = State()
    entering_phone = State()