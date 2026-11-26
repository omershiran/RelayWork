from alembic import context
from app.db import Base, engine
import app.work  # Registers commerce models for migration discovery.
import app.messaging
import app.negotiations
import app.orders
import app.payment_models
import app.delivery

with engine.connect() as connection:
    context.configure(connection=connection, target_metadata=Base.metadata)
    with context.begin_transaction():
        context.run_migrations()
