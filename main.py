import pandas as pd

from datetime import date
from datetime import datetime
from sqlalchemy import func, case, exc
from sqlalchemy.orm import sessionmaker
from fastapi import FastAPI, HTTPException, File, UploadFile
from models import engine, Credit, Payment, Dictionary, Plan


Session = sessionmaker(bind=engine)
db = Session()

app = FastAPI()


@app.get("/user_credits/{user_id}")
def get_user_credits(user_id: int):
    user_credits = db.query(
        Credit.issuance_date,
        Credit.actual_return_date,
        Credit.return_date,
        Credit.body,
        Credit.percent,
        func.sum(Payment.sum).label('total'),
        func.sum(case((Payment.type_id == 1, Payment.sum), else_=0)).label('payments_by_body'),
        func.sum(case((Payment.type_id == 2, Payment.sum), else_=0)).label('payments_by_percent')
    ).join(Credit.Payment
           ).filter(Credit.user_id == user_id
                    ).group_by(Payment.credit_id
                               ).all()

    # Отправка кода 404, при отсутствии кредитов пользователя
    if not user_credits:
        raise HTTPException(status_code=404, detail="Кредити користувача не знайдено")

    final_list = []

    for credit in user_credits:
        if credit.actual_return_date:
            # Закрытый кредит
            final_list.append({"issuance_date": credit.issuance_date.strftime("%Y-%m-%d"),
                               "is_closed": True,
                               "actual_return_date": credit.actual_return_date.strftime("%Y-%m-%d"),
                               "body": credit.body,
                               "percent": credit.percent,
                               "total_sum": round(credit.total, 2)
                               })
        else:
            # Открытый кредит
            final_list.append({"issuance_date": credit.issuance_date.strftime("%Y-%m-%d"),
                               "is_closed": False,
                               "return_date": credit.return_date.strftime("%Y-%m-%d"),
                               "days_overdue": (date.today() - credit.return_date).days,
                               "body": credit.body,
                               "percent": credit.percent,
                               "payments_by_body": round(credit.payments_by_body, 2),
                               "payments_by_percent": round(credit.payments_by_percent, 2)
                               })

    return {"user_credits": final_list}


def check_plan_exists(month, category_id):
    # Проверка наличия плана в БД
    return db.query(Plan).filter(Plan.period == month, Plan.category_id == category_id).first()


@app.post("/plans_insert")
def plans_insert(file: UploadFile = File(...)):
    # Чтение данных из Excel-файла
    df = pd.read_excel(file.file)

    # Проверка на правильность заполнения месяца плана
    for month in df['period']:
        try:
            datetime.strptime(str(month.date()), '%Y-%m-01')
        except ValueError:
            raise HTTPException(status_code=400, detail="Невірний формат місяця плану. Вказуйте перше число місяця.")

    id_dictionary = {"видача": 3, "збір": 4}

    # Проверка наличия плана в БД
    for index, row in df.iterrows():
        month = row['period']
        category_id = id_dictionary[row['category']]
        plan_exists = check_plan_exists(month, category_id)
        if plan_exists:
            raise HTTPException(status_code=400,
                                detail=f"План на місяць {month.date()} з категорією '{row['category']}' вже існує в базі даних.")

    # Преобразовать значения в столбце category в category_id
    df['category_id'] = df['category'].map(id_dictionary)

    # Удаляем столбец category, он для внесения данных в БД больше не нужен
    df.drop('category', axis=1, inplace=True)

    # Вставка данных в таблицу Plans
    try:
        df.to_sql('Plans', con=engine, if_exists='append', index=False)
    except exc.IntegrityError:
        raise HTTPException(status_code=500, detail="Помилка внесення даних до БД.")

    return {"message": "Дані з файлу успішно внесено до БД."}


@app.get("/plans_performance")
def get_plans_performance(target_date: date):
    try:
        # Определяем месяц и год из даты
        month = target_date.month
        year = target_date.year

        # Вариант ввода даты формата - YYYY-MM
        # # Находим максимальный день месяца
        # max_day = calendar.monthrange(year, month)[1]
        #
        # # Устанавливаем этот день
        # target_date = target_date.replace(day=max_day)

        # Выполняем запрос к базе данных для получения информации о планах на определенный месяц и год
        plans_info = db.query(Plan, Dictionary.name).join(Dictionary).filter(func.extract('year', Plan.period) == year, func.extract('month', Plan.period) == month).all()

        if not plans_info:
            raise HTTPException(status_code=404, detail="Планів на вказаний місяць не знайдено")

        final_list = []

        for plan, category_name in plans_info:
            # Вычисляем сумму виданных кредитов или сумму платежей для каждого плана
            if category_name == "видача":
                total_amount = db.query(func.sum(Credit.body)).filter(Credit.issuance_date >= datetime(year, month, 1), Credit.issuance_date <= target_date).scalar()
            else:
                total_amount = db.query(func.sum(Payment.sum)).filter(Payment.payment_date >= datetime(year, month, 1), Payment.payment_date <= target_date).scalar()

            if not total_amount:
                total_amount = 0

            # Вычисляем процент выполнения плана
            plan_completion_percent = (total_amount / plan.sum) * 100 if plan.sum != 0 else 0

            # Собираем информацию о выполнении плана
            plan_info = {
                "month": plan.period.strftime('%Y-%m-%d'),
                "category": category_name,
                "plan_amount": plan.sum,
                "total_amount": round(total_amount, 2),
                "completion_percent": round(plan_completion_percent, 2)
            }
            final_list.append(plan_info)

        return {"plans_performance": final_list}

    except ValueError:
        raise HTTPException(status_code=400, detail="Неправильний формат дати. Використовуйте формат 'YYYY-MM-DD'")


@app.get("/year_performance")
def get_year_performance(year: int):
    try:
        # Проверяем, что заданный год является корректным
        datetime(year, 1, 1)
    except ValueError:
        raise HTTPException(status_code=400, detail="Некоректний рік")

    # Создаем подзапрос для получения суммы з плану по видачам
    plan_sum_subquery = db.query(func.sum(Plan.sum)).filter(Dictionary.name == "видача")

    # Создаем подзапрос для получения суммы з плану по збору
    plan_collection_sum_subquery = db.query(func.sum(Plan.sum)).filter(Dictionary.name == "збір")

    # Выполняем SQL-запрос для получения сводной информации
    results = db.query(
        func.year(Credit.issuance_date).label("year"),
        func.month(Credit.issuance_date).label("month"),
        func.count(Credit.id_credit).label("num_credits"),
        plan_sum_subquery.label("plan_sum"),
        func.sum(Credit.body).label("sum_credits"),
        (func.sum(Credit.body) / func.sum(Plan.sum) * 100).label("plan_execution_percent"),
        func.count(Payment.id_payment).label("num_payments"),
        plan_collection_sum_subquery.label("plan_collection_sum"),
        func.sum(Payment.sum).label("sum_payments"),
        (func.sum(Payment.sum) / func.sum(Plan.sum) * 100).label("collection_execution_percent"),
        (func.sum(Credit.body) / func.sum(Credit.body).over(partition_by=func.year(Credit.issuance_date))).label("sum_credits_percent"),
        (func.sum(Payment.sum) / func.sum(Payment.sum).over(partition_by=func.year(Payment.payment_date))).label("sum_payments_percent"),
    ).join(Credit.Payment).filter(func.year(Credit.issuance_date) == year).group_by("month").all()

    # Обработка результатов и формирование сводной информации в нужном формате
    final_list = []
    for month in results:
        final_list.append({
            "year": month.year,
            "month": month.month,
            "num_credits": month.num_credits,
            "plan_sum": month.plan_sum,
            "sum_credits": month.sum_credits,
            "plan_execution_percent": round(month.plan_execution_percent, 2),
            "num_payments": month.num_payments,
            "plan_collection_sum": month.plan_collection_sum,
            "sum_payments": round(month.sum_payments, 2),
            "collection_execution_percent": round(month.collection_execution_percent),
            "sum_credits_percent": round(month.sum_credits_percent, 2),
            "sum_payments_percent": round(month.sum_payments_percent, 2)
        })

    return {"year_performance": final_list}