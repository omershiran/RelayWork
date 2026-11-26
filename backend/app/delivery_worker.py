from .auth import now
from .db import Database
from .delivery import auto_approve
from .payments import sandbox_provider


def main():
    sandbox_provider()
    with Database() as db:
        print(f"Sandbox automatic approvals: {auto_approve(db, now())}")


if __name__ == "__main__":
    main()
