from types import SimpleNamespace
from uuid import uuid4

import pytest

from app import buyer
from app.llm import Generation


@pytest.mark.parametrize(("text", "answer"), [("Calculate 8 × 7", "56"), ("חשב 3.5 / 2", "1.75"), ("2 * 0", "0")])
def test_calculation(text, answer):
    assert buyer.calculate(text) == answer


def test_model_can_answer_or_route_without_contacting_suppliers(monkeypatch):
    data = buyer.TurnInput(client_id=uuid4(), prompt="Please help me")
    agent = SimpleNamespace(owner=uuid4())
    generation = Generation("mock", 25, 12)
    monkeypatch.setattr(buyer, "model_route", lambda *_: (buyer.RouteAnswer(kind="answer", text="Here is a draft"), generation))
    assert buyer.execute(None, agent, data)["response"] == "Here is a draft"
    monkeypatch.setattr(buyer, "model_route", lambda *_: (buyer.RouteService(kind="service", keywords="printing"), generation))
    monkeypatch.setattr(buyer, "matches", lambda _, keywords, owner: [keywords, str(owner)])
    result = buyer.execute(None, agent, data)
    assert result["kind"] == "services"
    assert result["recommendations"] == ["printing", str(agent.owner)]
    assert result["input_tokens"] == 25
