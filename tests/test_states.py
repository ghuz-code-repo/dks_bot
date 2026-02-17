"""
Unit тесты для FSM состояний.
"""
import pytest
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from utils.states import ClientSteps
from aiogram.fsm.state import State


class TestClientSteps:
    """Тесты для состояний клиента"""
    

    def test_entering_contract_state_exists(self):
        """Состояние entering_contract существует"""
        assert hasattr(ClientSteps, 'entering_contract')
        assert isinstance(ClientSteps.entering_contract, State)
    
    def test_selecting_date_state_exists(self):
        """Состояние selecting_date существует"""
        assert hasattr(ClientSteps, 'selecting_date')
        assert isinstance(ClientSteps.selecting_date, State)
    
    def test_selecting_time_state_exists(self):
        """Состояние selecting_time существует"""
        assert hasattr(ClientSteps, 'selecting_time')
        assert isinstance(ClientSteps.selecting_time, State)
    
    def test_entering_phone_state_exists(self):
        """Состояние entering_phone существует"""
        assert hasattr(ClientSteps, 'entering_phone')
        assert isinstance(ClientSteps.entering_phone, State)
    
    def test_all_states_count(self):
        """Проверка количества состояний"""
        states = [
            ClientSteps.entering_contract,
            ClientSteps.selecting_date,
            ClientSteps.selecting_time,
            ClientSteps.entering_phone
        ]
        assert len(states) == 4
    
    def test_states_are_unique(self):
        """Все состояния уникальны"""
        states = [
            str(ClientSteps.entering_contract),
            str(ClientSteps.selecting_date),
            str(ClientSteps.selecting_time),
            str(ClientSteps.entering_phone)
        ]
        assert len(states) == len(set(states))


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
