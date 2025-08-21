from django.shortcuts import render
from django.contrib.auth import authenticate, login, logout
from django.http import HttpResponseRedirect
from django.urls import reverse
from django.db import IntegrityError
from django.contrib.auth.decorators import login_required
from datetime import datetime, timedelta
from dateutil.relativedelta import relativedelta
from django.core.paginator import Paginator
from django.db.models import Sum, Q

from .models import User, Company, CompanyUser, Category, Account, Transaction, MonthlyAccountBalance, Timer

# Settle function created to be used in different views to settle a transaction
# Transfer equals "F"(from) if it's the sending account, "T"(to) if it's the receiving account, None if it's a regular settle
def settle(transaction, request, transfer):
    message = None
    error = None
    came_from_income = False
    amount = request.POST["amount"]
    
    try:
        if transfer == "F":
            account = Account.objects.get(id=request.POST["from"])
        elif transfer == "T":
            account = Account.objects.get(id=request.POST["to"])
        else:
            account = Account.objects.get(id=request.POST["account_id"])
    except:
        account = None
        error = "Must select an account."
        if transaction.category.type == "I":
            came_from_income = True

    try:
        settle_description = request.POST["settle_description"]
    except:
        settle_description = ""

    # If it has not settle date, it means that it came from the settle check box on the new transaction page
    try:
        settle_date = request.POST["settle_date"]
    except:
        settle_date = request.POST["due_date"]

        # Added not transaction.settle_date as a server fail safe to double settlings when server is slow or the user refreshes the page
    if account and not transaction.settle_date:
        # Update transaction with settle information

        transaction.settle_description = settle_description
        transaction.amount = amount
        transaction.settle_date = settle_date
        transaction.settle_user = request.user
        transaction.settle_account = account
        transaction.save()

        date = datetime.strptime(settle_date, "%Y-%m-%d").replace(day=1).date()
        # Try to get an instance of the account's monthly balance, creates one if it doesn't exist
        try:
            monthly_balance = MonthlyAccountBalance.objects.get(account=account, month_year=date)
        except:
            monthly_balance = MonthlyAccountBalance(account=account, month_year=date)

        # Update account balance
        if transaction.category.type == "E":
            account.balance = float(account.balance) - float(amount)
            monthly_balance.balance = float(monthly_balance.balance) - float(amount)
        else:
            account.balance = float(account.balance) + float(amount)
            monthly_balance.balance = float(monthly_balance.balance) + float(amount)
            came_from_income = True

        account.save()
        monthly_balance.save()
        message = "Transaction settled successfully."
        
    return {"message":message, "error":error, "came_from_income":came_from_income}

# Replicate function for copy transaction and replicate to the next due_date, forced variable was created to force replication before transaction expired
def replicate(transaction, forced):
    today = datetime.today().date()
    if transaction.replicate == "M":
        months = 1
    elif transaction.replicate == "B":
        months = 2
    elif transaction.replicate == "Q":
        months = 3
    elif transaction. replicate == "Y":
        months = 12
    
    while transaction.due_date < today or forced:
        if forced:
            forced = False

        due_date = transaction.due_date + relativedelta(months=months)
        new_transaction = Transaction(company=transaction.company, user=transaction.user, due_date=due_date, category=transaction.category, amount=transaction.amount, payment_info=transaction.payment_info,
                                        description=transaction.description, replicate=transaction.replicate, installments=transaction.installments, current_installment=transaction.current_installment, parent_id=transaction.id)
        new_transaction.save()
        # Check if new transaction due_date should be last day of month, comparing with parent's transaction
        if transaction.is_last_day_of_month() and not new_transaction.is_last_day_of_month():
            try:
                parent_transaction = Transaction.objects.get(id=transaction.parent_id)
            except:
                parent_transaction = None
            if parent_transaction:
                if parent_transaction.is_last_day_of_month():
                    new_transaction.due_date = new_transaction.due_date.replace(day=1) + relativedelta(months=1) - relativedelta(days=1)
                    new_transaction.save()
            else:
                new_transaction.due_date = new_transaction.due_date.replace(day=1) + relativedelta(months=1) - relativedelta(days=1)
                new_transaction.save()

        if transaction.replicate == "Y" and transaction.installments:
            for i in range(2, int(transaction.installments)+1):
                new_transaction_installments = Transaction(company=transaction.company, user=transaction.user, due_date=new_transaction.due_date + relativedelta(months=i-1), category=transaction.category,
                                                            amount=transaction.amount, payment_info=transaction.payment_info, description=transaction.description, replicate=transaction.replicate, installments=transaction.installments, current_installment=i)
                new_transaction_installments.save()
            
        transaction.has_replicated = True
        transaction.save()
        transaction = new_transaction


def register(request):
    if request.method == "POST":
        username = request.POST["username"]
        email = request.POST["email"]
        company_name = request.POST["company"]

        # Ensure password matches confirmation
        password = request.POST["password"]
        confirmation = request.POST["confirmation"]
        if password != confirmation:
            return render(request, "core/register.html", {
                "error": "Passwords must match."
            })

        '''
        # Check if company name is taken
        if Company.objects.filter(name=company_name).exists():
            return render(request, "core/register.html", {
                "error": "Company name already taken."
            })
        '''

        # Attempt to create new user
        try:
            user = User.objects.create_user(username, email, password)
            user.save()
        except IntegrityError:
            return render(request, "core/register.html", {
                "error": "Username unavailable."
            })
        
        # Create company
        company = Company(name=company_name, user=user)
        company.save()

        # Create company-user relation
        company_user = CompanyUser(user=user, company=company, access_level=1)
        company_user.save()

        # Create basic transfer categories to be used in any company
        transfer_out_category = Category(name="Transfer Out", type="E", company=company)
        transfer_in_category = Category(name="Transfer In", type="I", company=company)
        transfer_out_category.save()
        transfer_in_category.save()
        
        # Create a database date stores for replicating purposes
        timer = Timer(db_date=datetime.today().date(), company=company)
        timer.save()

        login(request, user)
        companies = []
        for company in user.owned_companies.all():
            companies.append(company.name)
        request.session["company"] = user.owned_companies.all()[0].name
        request.session["company_id"] = user.owned_companies.all()[0].id
        request.session["companies"] = companies

        return HttpResponseRedirect(reverse("index"))
    else:
        return render(request, "core/register.html")


def login_view(request):
    if request.method == "POST":

        # Attempt to sign user in
        username = request.POST["username"]
        password = request.POST["password"]
        user = authenticate(request, username=username, password=password)
        # Check if authentication successful
        if user is not None:
            login(request, user)
            list_of_owned_companies = []
            owned_companies = user.owned_companies.all()
            for company in owned_companies:
                list_of_owned_companies.append(company.name)
            request.session["company"] = owned_companies[0].name
            request.session["company_id"] = owned_companies[0].id
            request.session["companies"] = list_of_owned_companies
            return HttpResponseRedirect(reverse("index"))
        else:
            return render(request, "core/login.html", {
                "error": "Invalid username and/or password."
            })
    else:
        return render(request, "core/login.html")
    

def logout_view(request):
    logout(request)
    return HttpResponseRedirect(reverse("index"))


@login_required
def index(request):
    timer = Timer.objects.get(company=request.session["company_id"])
    today = datetime.today().date()

    if (timer.db_date != today):
        timer.db_date = today
        timer.save()
        expired_transactions = Transaction.objects.filter(
            ~Q(replicate="O"), company=request.session["company_id"], due_date__lt=today, has_replicated=False).exclude(current_installment__gt=1)
        
        for transaction in expired_transactions:
            replicate(transaction, False)

    message = None
    error = None
    # By default the page loads on the expenses tab, this variable changes to the income tab if a form was sent from income
    came_from_income = False 
    if request.method == "POST":
        if request.POST["action"] == "settle":
            transaction = Transaction.objects.get(id=request.POST["transaction_id"])
            ret = settle(transaction, request, False)
            message = ret["message"]
            error = ret["error"]
            came_from_income = ret["came_from_income"]
        elif request.POST["action"] == "update_range":
            request.session["upcoming_range"] = request.POST["upcoming_range"]

    try:
        upcoming_range = int(request.session["upcoming_range"])
    except:
        upcoming_range = 15
        request.session["upcoming_range"] = 15

    upcoming_range_iterator = [15,30,45,60]
    accounts = Account.objects.filter(company=request.session["company_id"])
    upcoming = today + timedelta(upcoming_range)
    todays_expenses = Transaction.objects.filter(category__type="E", due_date__lte=today, company=request.session["company_id"], settle_date__isnull=True).order_by("due_date")
    todays_expenses_total = todays_expenses.aggregate(Sum("amount"))["amount__sum"]
    upcoming_expenses = Transaction.objects.filter(category__type="E", due_date__range=(today+timedelta(1), upcoming), company=request.session["company_id"], settle_date__isnull=True).order_by("due_date")
    upcoming_expenses_total = upcoming_expenses.aggregate(Sum("amount"))["amount__sum"]
    settled_expenses = Transaction.objects.filter(category__type="E", company=request.session["company_id"], settle_date=today).order_by("due_date")
    settled_expenses_total = settled_expenses.aggregate(Sum("amount"))["amount__sum"]
    todays_incomes = Transaction.objects.filter(category__type="I", due_date__lte=today, company=request.session["company_id"], settle_date__isnull=True).order_by("due_date")
    todays_incomes_total = todays_incomes.aggregate(Sum("amount"))["amount__sum"]
    upcoming_incomes = Transaction.objects.filter(category__type="I", due_date__range=(today+timedelta(1), upcoming), company=request.session["company_id"], settle_date__isnull=True).order_by("due_date")
    upcoming_incomes_total = upcoming_incomes.aggregate(Sum("amount"))["amount__sum"]
    settled_incomes = Transaction.objects.filter(category__type="I", company=request.session["company_id"], settle_date=today).order_by("due_date")
    settled_incomes_total = settled_incomes.aggregate(Sum("amount"))["amount__sum"]
    
    return render(request, "core/index.html", {
        "upcoming_range": upcoming_range,
        "upcoming_range_iterator": upcoming_range_iterator,
        "accounts": accounts,
        "todays_expenses": todays_expenses,
        "todays_expenses_total": todays_expenses_total,
        "upcoming_expenses": upcoming_expenses,
        "upcoming_expenses_total": upcoming_expenses_total,
        "settled_expenses": settled_expenses,
        "settled_expenses_total": settled_expenses_total,
        "todays_incomes": todays_incomes,
        "todays_incomes_total": todays_incomes_total,
        "upcoming_incomes": upcoming_incomes,
        "upcoming_incomes_total": upcoming_incomes_total,
        "settled_incomes": settled_incomes,
        "settled_incomes_total": settled_incomes_total,
        "came_from_income": came_from_income,
        "today": today,
        "message": message,
        "error": error
    })


@login_required
def new_transaction(request):
    expense_categories = Category.objects.filter(type="E", company=request.session["company_id"]).order_by("name")
    income_categories = Category.objects.filter(type="I", company=request.session["company_id"]).order_by("name")
    accounts = Account.objects.filter(company=request.session["company_id"])
    message = None
    error = None

    if request.method == "POST":
        due_date = datetime.strptime(request.POST["due_date"], "%Y-%m-%d").date()
        amount = float(request.POST["amount"])
        payment_info = request.POST["payment_info"]
        description = request.POST["description"]
        replicate = request.POST["replicate"]
        has_installments = request.POST.get("has_installments", False)
        installments = request.POST["installments"]
        company = Company.objects.get(id=request.session["company_id"])
        is_settle = request.POST.get("settle", False)
        is_transfer = request.POST.get("transfer", False)
        if not is_transfer:
            try:
                category = Category.objects.get(id=request.POST["category"])
            except:
                return render(request, "core/new_transaction.html", {"expense_categories": expense_categories, "income_categories": income_categories, "accounts": accounts, "error":"Must choose category."})
            
            if has_installments and int(installments) > 12 and replicate != "O":
                error = "Transactions with more than 12 installments can't replicate."
            elif has_installments:
                for n in range(int(installments)):
                    transaction = Transaction(company=company, user=request.user, due_date=due_date + relativedelta(months=n), category=category, amount=amount,
                                            payment_info=payment_info, description=description, replicate=replicate, installments=installments, current_installment=int(n)+1)
                    transaction.save()
            else:
                transaction = Transaction(company=company, user=request.user, due_date=due_date, category=category,
                                        amount=amount, payment_info=payment_info, description=description, replicate=replicate)
                transaction.save()

        if is_settle:
            ret = settle(transaction, request, False)
            error = ret["error"]
        elif is_transfer:
            transaction_from = Transaction(company=company, user=request.user, due_date=due_date, category=Category.objects.get(name="Transfer Out", company=company),
                                        amount=amount, payment_info=payment_info, description=description, replicate=replicate)
            transaction_to = Transaction(company=company, user=request.user, due_date=due_date, category=Category.objects.get(name="Transfer In", company=company),
                                        amount=amount, payment_info=payment_info, description=description, replicate=replicate)
            transaction_from.save()
            transaction_to.save()
            ret = settle(transaction_from, request, "F")
            ret = settle(transaction_to, request, "T")
            error = ret["error"]

        message = "Transaction saved successfully."

    today = datetime.today().date()
    return render(request, "core/new_transaction.html", {
        "expense_categories": expense_categories,
        "income_categories": income_categories,
        "accounts": accounts,
        "today": today,
        "message": message,
        "error": error
    })


@login_required
def archive(request):
    if request.method == "POST":
        try:
            from_date = datetime.strptime(request.POST["from_date"], "%Y-%m-%d").date()
        except ValueError:
            from_date = None
        try:
            to_date = datetime.strptime(request.POST["to_date"], "%Y-%m-%d").date()
        except ValueError:
            to_date = None
        search = request.POST["search"]
        is_unsettled = request.POST["is_unsettled"]
        expense_income_option = request.POST["expense_income_option"]

        search_data = Transaction.objects.filter(company= request.session["company_id"], description__icontains=search, category__type=expense_income_option, settle_date__isnull=bool(is_unsettled))

        if is_unsettled:
            if from_date:
                search_data = search_data.filter(due_date__gte=from_date)
            if to_date:
                search_data = search_data.filter(due_date__lte=to_date)
            search_data = search_data.order_by("due_date")
        else:
            if from_date:
                search_data = search_data.filter(settle_date__gte=from_date)
            if to_date:
                search_data = search_data.filter(settle_date__lte=to_date)
            search_data = search_data.order_by("-settle_date")

        data_paginator = Paginator(search_data, 15)
        try:
            page_num = request.POST['page']
        except:
            page_num = None
        page = data_paginator.get_page(page_num)
        iterator = range(1, page.paginator.num_pages+1)
        max_page = max(iterator)

        search_parameters = {
            "from": request.POST["from_date"],
            "to": request.POST["to_date"],
            "is_unsettled": is_unsettled,
            "expense_income_option": expense_income_option
        }

        # I had to take "search" out of the search_parameters dictionary because Django template couldn't handle strings with more than 1 word
        return render(request, "core/archive.html", {
            "search": search,
            "search_parameters": search_parameters,
            "page": page,
            "iterator": iterator,
            "max_page": max_page
        })

    return render(request, "core/archive.html")


@login_required
def edit(request):
    if request.method == "POST" and not request.POST["edit"] == "copy_transaction":
        transaction = Transaction.objects.get(id=request.POST["transaction_id"])
        old_amount = float(transaction.amount)
        
        try:
            account = Account.objects.get(id=request.POST["account"])
        except:
            account = None

        try:
            apply_to_next_installments = request.POST["apply_to_next_installments"]
        except:
            apply_to_next_installments = None

        if request.POST["edit"] == "edit_transaction":
            due_date = datetime.strptime(request.POST["due_date"], "%Y-%m-%d").date()
            try:
                settle_date = datetime.strptime(request.POST["settle_date"], "%Y-%m-%d").date()
                old_settle_month_year = transaction.settle_date.replace(day=1)
            except:
                settle_date = None

            try:
                settle_description = request.POST["settle_description"]
            except:
                settle_description = None

            category = Category.objects.get(id=request.POST["category"])
            amount = float(request.POST["amount"])
            payment_info = request.POST["payment_info"]
            description = request.POST["description"]
            transaction.due_date = due_date
            transaction.settle_date = settle_date
            transaction.category = category
            transaction.amount = amount
            transaction.payment_info = payment_info
            transaction.description = description
            transaction.settle_description = settle_description
            transaction.save()
            message = "Transaction edited successfully."

            # Update future installments amount and description, if apply_to_next_installments checked
            if (apply_to_next_installments):
                count = 1
                for _ in range(transaction.current_installment+1, transaction.installments+1):
                    next_transaction = Transaction.objects.get(id=transaction.id+count)
                    next_transaction.description = transaction.description
                    next_transaction.payment_info = transaction.payment_info
                    next_transaction.amount = transaction.amount
                    next_transaction.category = transaction.category
                    next_transaction.save()
                    count = count + 1

            # Check if transaction has been settled and adjust account balance
            if (transaction.settle_date):
                old_account = Account.objects.get(id=transaction.settle_account.id)
                if (transaction.settle_account != account):
                    if (transaction.category.type == "E"):
                        old_account.balance = float(old_account.balance) + old_amount
                        account.balance = float(account.balance) - transaction.amount
                    else:
                        old_account.balance = float(old_account.balance) - old_amount
                        account.balance = float(account.balance) + transaction.amount
                    old_account.save()
                    account.save()
                    transaction.settle_account = account

                elif (old_amount != amount):
                    if (transaction.category.type == "E"):
                        account.balance = float(account.balance) + old_amount
                        account.balance = float(account.balance) - amount
                    else:
                        account.balance = float(account.balance) - old_amount
                        account.balance = float(account.balance) + amount
                    account.save()

                old_account_monthly_balance = MonthlyAccountBalance.objects.get(account=old_account, month_year=old_settle_month_year)
                try:
                    account_monthly_balance = MonthlyAccountBalance.objects.get(account=account, month_year=settle_date.replace(day=1))
                except:
                    account_monthly_balance = MonthlyAccountBalance(account=account, month_year=settle_date.replace(day=1))

                # This conditional checks if the account or month is different
                if (old_account_monthly_balance != account_monthly_balance):
                    if (transaction.category.type == "E"):
                        old_account_monthly_balance.balance = float(old_account_monthly_balance.balance) + old_amount
                        account_monthly_balance.balance = float(account_monthly_balance.balance) - amount
                    else:
                        old_account_monthly_balance.balance = float(old_account_monthly_balance.balance) - old_amount
                        account_monthly_balance.balance = float(account_monthly_balance.balance) + amount
                    
                    old_account_monthly_balance.save()
                    account_monthly_balance.save()

                elif (old_amount != amount):
                    if (transaction.category.type == "E"):
                        account_monthly_balance.balance = float(account_monthly_balance.balance) + old_amount
                        account_monthly_balance.balance = float(account_monthly_balance.balance) - amount
                    else:
                        account_monthly_balance.balance = float(account_monthly_balance.balance) - old_amount
                        account_monthly_balance.balance = float(account_monthly_balance.balance) + amount
                    account_monthly_balance.save()

                transaction.save()
                
       
        elif request.POST["edit"] == "delete_transaction":
            if (transaction.settle_date):
                account_monthly_balance = MonthlyAccountBalance.objects.get(account=account, month_year=transaction.settle_date.replace(day=1))
                if (transaction.category.type == "E"):
                    account.balance = float(account.balance) + old_amount
                    account_monthly_balance.balance = float(account_monthly_balance.balance) + old_amount
                else:
                    account.balance = float(account.balance) - old_amount
                    account_monthly_balance.balance = float(account_monthly_balance.balance) - old_amount
                account.save()
                account_monthly_balance.save()

            if (apply_to_next_installments):
                count = 1
                for _ in range(transaction.current_installment+1, transaction.installments+1):
                    try:
                        next_transaction = Transaction.objects.get(id=transaction.id+count)
                        next_transaction.delete()
                    except:
                        pass
                    count = count + 1

            transaction.delete()
            message = "Transaction deleted successfully."

        elif request.POST["edit"] == "replicate":
            replicate(transaction, True)
            message = "Transaction replicated successfully."

        return render(request, "core/archive.html", {
            "message": message
        })
        
    try:
        transaction = Transaction.objects.get(id=request.GET.get("transaction_id"))
    except:
        transaction = Transaction.objects.get(id=request.POST["transaction_id"])

    if transaction.company.id != request.session["company_id"]:
        return render(request, "core/archive.html", {
            "error": "Access denied."
        })

    if (transaction.category.type == "E"):
        categories = Category.objects.filter(type="E", company=request.session["company_id"]).order_by("name")
    else:
        categories = Category.objects.filter(type="I", company=request.session["company_id"]).order_by("name")
        
    if request.method == "POST" and request.POST["edit"] == "copy_transaction":
        today = datetime.today().date()
        accounts = Account.objects.filter(company=request.session["company_id"]).order_by("name")
        return render(request, "core/new_transaction.html", {
            "accounts": accounts,
            "transaction": transaction,
            "categories": categories,
            "today": today
        })
    
    accounts = Account.objects.filter(company=request.session["company_id"])
    return render(request, "core/edit.html", {
        "transaction": transaction,
        "accounts": accounts,
        "categories": categories
    })


@login_required
def accounts(request):
    today = datetime.today().date()
    error = None
    
    if request.method == "POST":
        account = Account.objects.get(id=request.POST["account"])
        date = datetime.strptime(request.POST["date"], "%Y-%m").date().replace(day=1)
        transactions = Transaction.objects.filter(settle_account=account, settle_date__month=date.month, settle_date__year=date.year).order_by("settle_date")
        if not transactions:
            error = "No activity for the selected month"
        else:
            month_difference = relativedelta(today, date)
            month_difference = month_difference.years * 12 + month_difference.months
            month_balance = float(MonthlyAccountBalance.objects.get(account=account, month_year=date).balance)
            carry_over = 0
            for i in range(month_difference):
                try:
                    carry_over = carry_over + float(MonthlyAccountBalance.objects.get(account=account, month_year=date+relativedelta(months=i+1)).balance)
                except:
                    pass
            carry_over = float(account.balance) - (carry_over + month_balance)
            balance = carry_over + month_balance

        
            return render(request, "core/account_statement.html", {
                "account": account,
                "transactions": transactions,
                "carry_over": carry_over,
                "month_balance": month_balance,
                "balance": balance,
                "date": date.strftime("%B %Y")
            })

    accounts = Account.objects.filter(company=request.session["company_id"]).order_by("name")
    total_balance = accounts.aggregate(Sum("balance"))["balance__sum"]
    return render(request, "core/accounts.html", {
        "accounts": accounts,
        "total_balance": total_balance,
        "today": today,
        "error": error
    })

@login_required
def overview(request):
    ''' Get all relevant data related to the selected month'''
    error = None
    if request.method == "POST":
        date = datetime.strptime(request.POST["date"], "%Y-%m").date().replace(day=1)
        end_of_month = date + relativedelta(months=1) - relativedelta(days=1)
        current_month = datetime.today().date().replace(day=1)
        expense_categories = Category.objects.filter(~Q(name="Transfer Out"), type="E", company=request.session["company_id"]).order_by("name")
        income_categories = Category.objects.filter(~Q(name="Transfer In"), type="I", company=request.session["company_id"]).order_by("name")
        expense_month_balance = Transaction.objects.filter(~Q(category__name="Transfer Out"), category__type="E", company=request.session["company_id"], settle_date__gte=date, settle_date__lte=end_of_month).aggregate(Sum("amount"))["amount__sum"] or 0
        income_month_balance = Transaction.objects.filter(~Q(category__name="Transfer In"), category__type="I", company=request.session["company_id"], settle_date__gte=date, settle_date__lte=end_of_month).aggregate(Sum("amount"))["amount__sum"] or 0
        # Check if selected date is of the future, in this case, unsettled transactions of current and past months should be ignore in future projections, as they may yet be settled in current month (past months unsettled transactions are always shown in current month overview)
        if date > current_month:
            projected_expense_month_balance = Transaction.objects.filter(~Q(category__name="Transfer Out"), category__type="E", company=request.session["company_id"], due_date__gte=date, due_date__lte=end_of_month, settle_date__isnull=True).aggregate(Sum("amount"))["amount__sum"] or 0
            projected_income_month_balance = Transaction.objects.filter(~Q(category__name="Transfer In"), category__type="I", company=request.session["company_id"], due_date__gte=date, due_date__lte=end_of_month, settle_date__isnull=True).aggregate(Sum("amount"))["amount__sum"] or 0
        else:
            # Projected balance considers everything that has been settled in the selected month plus everything that hasn't been settled yet with due dates within the selected date
            projected_expense_month_balance = Transaction.objects.filter(~Q(category__name="Transfer Out"), category__type="E", company=request.session["company_id"], due_date__lte=end_of_month, settle_date__isnull=True).aggregate(Sum("amount"))["amount__sum"] or 0 
            projected_expense_month_balance = projected_expense_month_balance + expense_month_balance
            projected_income_month_balance = Transaction.objects.filter(~Q(category__name="Transfer In"), category__type="I", company=request.session["company_id"], due_date__lte=end_of_month, settle_date__isnull=True).aggregate(Sum("amount"))["amount__sum"] or 0
            projected_income_month_balance = projected_income_month_balance + income_month_balance
        expense_data = []
        income_data = []
        projected_expense_data = []
        projected_income_data = []
        for category in expense_categories:
            transactions = Transaction.objects.filter(category=category, settle_date__gte=date, settle_date__lte=end_of_month).order_by("-amount")
            category_amount = transactions.aggregate(Sum("amount"))["amount__sum"] or 0
            if category_amount:
                data = {}
                data["id"] = category.id
                data["name"] = category.name
                data["amount"] = category_amount
                data["percent"] = category_amount / expense_month_balance * 100
                data["transactions"] = transactions
                expense_data.append(data)

            if date >= current_month:
                if date > current_month:
                    projected_transactions = Transaction.objects.filter(category=category, due_date__gte=date, due_date__lte=end_of_month, settle_date__isnull=True).order_by("due_date")
                    projected_category_amount = projected_transactions.aggregate(Sum("amount"))["amount__sum"] or 0
                    projected_category_amount = projected_category_amount
                else:
                    projected_transactions = Transaction.objects.filter(category=category, due_date__lte=end_of_month, settle_date__isnull=True).order_by("due_date")
                    projected_category_amount = projected_transactions.aggregate(Sum("amount"))["amount__sum"] or 0
                    projected_category_amount = projected_category_amount + category_amount

                if projected_category_amount:
                    projected_data = {}
                    projected_data["id"] = category.id + 0.1
                    projected_data["name"] = category.name
                    projected_data["amount"] = projected_category_amount
                    projected_data["percent"] = projected_category_amount / projected_expense_month_balance * 100
                    if date == current_month:
                        projected_data["transactions"] = transactions
                    projected_data["projected_transactions"] = projected_transactions
                    projected_expense_data.append(projected_data)
            
        for category in income_categories:
            transactions = Transaction.objects.filter(category=category, settle_date__gte=date, settle_date__lte=end_of_month).order_by("-amount")
            category_amount = transactions.aggregate(Sum("amount"))["amount__sum"] or 0
            if category_amount:
                data = {}
                data["id"] = category.id
                data["name"] = category.name
                data["amount"] = category_amount
                data["percent"] = category_amount / income_month_balance * 100
                data["transactions"] = transactions
                income_data.append(data)

            if date >= current_month:
                if date > current_month:
                    projected_transactions = Transaction.objects.filter(category=category, due_date__gte=date, due_date__lte=end_of_month, settle_date__isnull=True).order_by("due_date")
                    projected_category_amount = projected_transactions.aggregate(Sum("amount"))["amount__sum"] or 0
                    projected_category_amount = projected_category_amount
                else:
                    projected_transactions = Transaction.objects.filter(category=category, due_date__lte=end_of_month, settle_date__isnull=True).order_by("due_date")
                    projected_category_amount = projected_transactions.aggregate(Sum("amount"))["amount__sum"] or 0
                    projected_category_amount = projected_category_amount + category_amount
                if projected_category_amount:
                    projected_data = {}
                    projected_data["id"] = category.id + 0.1
                    projected_data["name"] = category.name
                    projected_data["amount"] = projected_category_amount
                    projected_data["percent"] = projected_category_amount / projected_income_month_balance * 100
                    if date == current_month:
                        projected_data["transactions"] = transactions
                    projected_data["projected_transactions"] = projected_transactions
                    projected_income_data.append(projected_data)
            
        expense_data = sorted(expense_data, key=lambda d: d['percent'], reverse=True)
        income_data = sorted(income_data, key=lambda d: d['percent'], reverse=True)
        projected_expense_data = sorted(projected_expense_data, key=lambda d: d['percent'], reverse=True)
        projected_income_data = sorted(projected_income_data, key=lambda d: d['percent'], reverse=True)
        expense_income_exists = expense_data or income_data
        projected_exists = projected_expense_data or projected_income_data
        if (expense_data or income_data or projected_expense_data or projected_income_data):
            return render(request, "core/overview.html", {
                "date": date.strftime("%B %Y"),
                "expense_data": expense_data,
                "income_data": income_data,
                "projected_expense_data": projected_expense_data,
                "projected_income_data": projected_income_data,
                "expense_month_balance": expense_month_balance,
                "income_month_balance": income_month_balance,
                "projected_expense_month_balance": projected_expense_month_balance,
                "projected_income_month_balance": projected_income_month_balance,
                "month_result": income_month_balance - expense_month_balance,
                "projected_month_result": projected_income_month_balance - projected_expense_month_balance,
                "expense_income_exists": expense_income_exists,
                "projected_exists": projected_exists
            })
        else:
            error = "No activity for the selected month"
    
    accounts = Account.objects.filter(company=request.session["company_id"]).order_by("name")
    return render(request, "core/overview.html", {
        "accounts": accounts,
        "error": error
    })

@login_required
def settings(request):
    message = None
    error = None
    if request.method == "POST":
        company = Company.objects.get(name=request.session["company"])
        # Save new category
        if request.POST["option"] == "new_category":
            new_category = request.POST["new_category"].title()
            type = request.POST["category_type"]
            category = Category(name=new_category, type=type, company=company)
            try:
                category.save()
                message = "New category saved."
            except IntegrityError:
                error = "Category name unavailable."

        
        # Save new account
        elif request.POST["option"] == "new_account":
            new_account = request.POST["new_account"].title()
            starting_balance = float(request.POST["starting_balance"])
            account = Account(name=new_account, balance=starting_balance, company=company)
            try:
                account.save()
                message = "New account saved."
            except IntegrityError:
                error = "Account name unavailable."

        elif request.POST["option"] == "new_company":
            new_company = request.POST["new_company"]
            # Create company
            try:
                company = Company(name=new_company, user=request.user)
                company.save()
            except IntegrityError:
                return render(request, "core/settings.html", {
                    "error": "Company name must be different."
                })

            # Create company-user relation
            company_user = CompanyUser(user=request.user, company=company)
            company_user.save()

            # Create basic transfer categories to be used in any company
            transfer_out_category = Category(name="Transfer Out", type="E", company=company)
            transfer_in_category = Category(name="Transfer In", type="I", company=company)
            transfer_out_category.save()
            transfer_in_category.save()

            # Create a database date stored for replicating purposes
            timer = Timer(db_date=datetime.today().date(), company=company)
            timer.save()
            companies = request.session["companies"]
            companies.append(company.name)
            request.session["companies"] = companies
            message = "New company saved."

        elif request.POST["option"] == "change_password":
            current_password = request.POST["current_password"]
            new_password = request.POST["new_password"]
            confirmation = request.POST["confirmation"]
            user = request.user
            
            if user.check_password(current_password):
                if new_password != confirmation:
                    error = "Passwords must match."
                else:
                    user.set_password(new_password)
                    user.save()
                    message = "Password changed successfully."
            else:
                error = "Incorrect password."

    return render(request, "core/settings.html", {
        "message": message,
        "error": error,
    })

@login_required
def swap_company(request):
    selected_company = Company.objects.get(name=request.POST["selected_company"], user=request.user)
    request.session["company"] = selected_company.name
    request.session["company_id"] = selected_company.id
    return HttpResponseRedirect(reverse("index"))