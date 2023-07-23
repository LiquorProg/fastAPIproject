from sqlalchemy import ForeignKey, Column, Integer, String, Date, Float, create_engine
from sqlalchemy.orm import relationship, declarative_base

from config import DB_NAME, DB_PASS, DB_USER


# информация о данных в БД
Base = declarative_base()


class User(Base):
    __tablename__ = "Users"

    id_user = Column(Integer, primary_key=True)
    login = Column(String(250))
    registration_date = Column(Date)
    Credit = relationship("Credit")


class Credit(Base):
    __tablename__ = "Credits"

    id_credit = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("Users.id_user"))
    issuance_date = Column(Date, nullable=True)
    return_date = Column(Date, nullable=True)
    actual_return_date = Column(Date, nullable=True)
    body = Column(Float)
    percent = Column(Float)
    User = relationship("User")
    Payment = relationship("Payment")

class Payment(Base):
    __tablename__ = "Payments"

    id_payment = Column(Integer, primary_key=True)
    sum = Column(Float)
    payment_date = Column(Date)
    credit_id = Column(Integer, ForeignKey("Credits.id_credit"))
    type_id = Column(Integer, ForeignKey("Dictionary.id_dictionary"))
    Credit = relationship("Credit")
    Dictionary = relationship("Dictionary")


class Plan(Base):
    __tablename__ = "Plans"

    id_plan = Column(Integer, primary_key=True)
    period = Column(Date)
    sum = Column(Float)
    category_id = Column(Integer, ForeignKey("Dictionary.id_dictionary"))
    Dictionary = relationship("Dictionary")


class Dictionary(Base):
    __tablename__ = "Dictionary"

    id_dictionary = Column(Integer, primary_key=True)
    name = Column(String(250))
    Plan = relationship("Plan")
    Payment = relationship("Payment")


engine = create_engine(f"mysql+mysqlconnector://{DB_USER}:{DB_PASS}@localhost/{DB_NAME}")
Base.metadata.create_all(engine)

