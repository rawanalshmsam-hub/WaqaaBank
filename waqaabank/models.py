import uuid
from decimal import Decimal
from django.db import models


# ============================================================
# 1) Client — عميل البنك
# ============================================================
class Client(models.Model):
    STATUS_CHOICES = [
        ('pending_kyc', 'Pending KYC'),
        ('active', 'Active'),
        ('suspended', 'Suspended'),
        ('closed', 'Closed'),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)

    full_name = models.TextField()
    national_id_hmac = models.TextField(unique=True)
    phone_hmac = models.TextField(unique=True)
    email_hmac = models.TextField(unique=True, null=True, blank=True)

    date_of_birth = models.DateField(null=True, blank=True)

    username = models.CharField(max_length=150, unique=True)
    password_hash = models.TextField()

    failed_login_attempts = models.IntegerField(default=0)
    locked_until = models.DateTimeField(null=True, blank=True)

    # ربط مع وقاء
    waqaa_user_id = models.UUIDField(unique=True, null=True, blank=True)
    waqaa_linked_at = models.DateTimeField(null=True, blank=True)

    status = models.CharField(max_length=30, choices=STATUS_CHOICES, default='pending_kyc')
    kyc_verified = models.BooleanField(default=False)
    kyc_verified_at = models.DateTimeField(null=True, blank=True)

    last_login_at = models.DateTimeField(null=True, blank=True)
    last_login_ip = models.GenericIPAddressField(null=True, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'clients'

    def __str__(self):
        return self.username


# ============================================================
# 2) Account — حساب بنكي
# ============================================================
class Account(models.Model):
    ACCOUNT_TYPE_CHOICES = [
        ('checking', 'Checking'),
        ('savings', 'Savings'),
        ('investment', 'Investment'),
    ]

    STATUS_CHOICES = [
        ('active', 'Active'),
        ('frozen', 'Frozen'),
        ('closed', 'Closed'),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)

    client = models.ForeignKey(
        Client,
        on_delete=models.RESTRICT,
        related_name='accounts'
    )

    account_type = models.CharField(max_length=30, choices=ACCOUNT_TYPE_CHOICES)
    account_number = models.CharField(max_length=50, unique=True)
    iban = models.CharField(max_length=34, unique=True, null=True, blank=True)

    balance = models.DecimalField(max_digits=15, decimal_places=2, default=Decimal('0.00'))
    currency = models.CharField(max_length=3, default='SAR')

    daily_limit = models.DecimalField(max_digits=15, decimal_places=2, default=Decimal('50000.00'))
    single_limit = models.DecimalField(max_digits=15, decimal_places=2, default=Decimal('10000.00'))
    daily_spent = models.DecimalField(max_digits=15, decimal_places=2, default=Decimal('0.00'))
    daily_spent_reset_at = models.DateTimeField(null=True, blank=True)

    # أي مبلغ فوقه يحتاج تحقق من وقاء
    waqaa_threshold = models.DecimalField(max_digits=15, decimal_places=2, default=Decimal('1000.00'))

    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='active')
    freeze_reason = models.TextField(null=True, blank=True)
    frozen_at = models.DateTimeField(null=True, blank=True)
    frozen_by = models.TextField(null=True, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'accounts'

    def __str__(self):
        return f"{self.client.username} — {self.account_number}"


# ============================================================
# 3) Transaction — معاملة مالية
# ============================================================
class Transaction(models.Model):
    TYPE_CHOICES = [
        ('transfer', 'Transfer'),
        ('deposit', 'Deposit'),
        ('withdrawal', 'Withdrawal'),
        ('bill_payment', 'Bill Payment'),
    ]

    STATUS_CHOICES = [
        ('pending', 'Pending'),
        ('requires_verification', 'Requires Verification'),
        ('processing', 'Processing'),
        ('completed', 'Completed'),
        ('failed', 'Failed'),
        ('cancelled', 'Cancelled'),
        ('reversed', 'Reversed'),
    ]

    WAQAA_STATUS_CHOICES = [
        ('pending', 'Pending'),
        ('verified', 'Verified'),
        ('failed', 'Failed'),
        ('expired', 'Expired'),
        ('cancelled', 'Cancelled'),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)

    from_account = models.ForeignKey(
        Account,
        on_delete=models.RESTRICT,
        related_name='sent_transactions',
        null=True,
        blank=True
    )
    to_account = models.ForeignKey(
        Account,
        on_delete=models.RESTRICT,
        related_name='received_transactions',
        null=True,
        blank=True
    )

    transaction_type = models.CharField(max_length=30, choices=TYPE_CHOICES)
    amount = models.DecimalField(max_digits=15, decimal_places=2)
    currency = models.CharField(max_length=3, default='SAR')
    description = models.TextField(null=True, blank=True)

    reference_number = models.CharField(max_length=100, unique=True)
    idempotency_key = models.CharField(max_length=150, unique=True, null=True, blank=True)

    status = models.CharField(max_length=30, choices=STATUS_CHOICES, default='pending')

    # ربط وقاء
    requires_waqaa = models.BooleanField(default=False)
    waqaa_session_id = models.UUIDField(null=True, blank=True)
    waqaa_status = models.CharField(max_length=20, choices=WAQAA_STATUS_CHOICES, null=True, blank=True)
    waqaa_verified_at = models.DateTimeField(null=True, blank=True)
    waqaa_verified_by = models.TextField(null=True, blank=True)

    requested_at = models.DateTimeField(auto_now_add=True)
    expires_at = models.DateTimeField(null=True, blank=True)

    failure_reason = models.TextField(null=True, blank=True)
    failed_at = models.DateTimeField(null=True, blank=True)

    initiated_by_ip = models.GenericIPAddressField(null=True, blank=True)
    completed_at = models.DateTimeField(null=True, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'transactions'

    def __str__(self):
        return f"{self.reference_number} — {self.amount} {self.currency}"


# ============================================================
# 4) Card — بطاقة بنكية
# ============================================================
class Card(models.Model):
    CARD_TYPE_CHOICES = [
        ('debit', 'Debit'),
        ('credit', 'Credit'),
        ('prepaid', 'Prepaid'),
    ]

    STATUS_CHOICES = [
        ('inactive', 'Inactive'),
        ('active', 'Active'),
        ('blocked', 'Blocked'),
        ('expired', 'Expired'),
        ('cancelled', 'Cancelled'),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)

    account = models.ForeignKey(
        Account,
        on_delete=models.RESTRICT,
        related_name='cards'
    )

    card_type = models.CharField(max_length=20, choices=CARD_TYPE_CHOICES)
    last_four = models.CharField(max_length=4)
    card_number_hash = models.TextField(unique=True)

    expiry_date = models.DateField()
    cardholder_name = models.TextField()

    daily_limit = models.DecimalField(max_digits=15, decimal_places=2, default=Decimal('5000.00'))
    credit_limit = models.DecimalField(max_digits=15, decimal_places=2, null=True, blank=True)

    is_online_enabled = models.BooleanField(default=True)
    is_international = models.BooleanField(default=False)

    pin_hash = models.TextField(null=True, blank=True)
    failed_pin_attempts = models.IntegerField(default=0)
    pin_locked_until = models.DateTimeField(null=True, blank=True)

    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='inactive')
    blocked_reason = models.TextField(null=True, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'cards'

    def __str__(self):
        return f"{self.card_type} — **** {self.last_four}"


# ============================================================
# 5) Bill — فاتورة
# ============================================================
class Bill(models.Model):
    STATUS_CHOICES = [
        ('pending', 'Pending'),
        ('paid', 'Paid'),
        ('failed', 'Failed'),
        ('cancelled', 'Cancelled'),
    ]

    WAQAA_STATUS_CHOICES = [
        ('pending', 'Pending'),
        ('verified', 'Verified'),
        ('failed', 'Failed'),
        ('expired', 'Expired'),
        ('cancelled', 'Cancelled'),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)

    client = models.ForeignKey(
        Client,
        on_delete=models.RESTRICT,
        related_name='bills'
    )
    account = models.ForeignKey(
        Account,
        on_delete=models.RESTRICT,
        related_name='bills'
    )

    biller_name = models.TextField()
    biller_code = models.CharField(max_length=50)
    bill_number = models.CharField(max_length=100)

    amount = models.DecimalField(max_digits=15, decimal_places=2)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending')

    requires_waqaa = models.BooleanField(default=False)
    waqaa_session_id = models.UUIDField(null=True, blank=True)
    waqaa_status = models.CharField(max_length=20, choices=WAQAA_STATUS_CHOICES, null=True, blank=True)

    due_date = models.DateField(null=True, blank=True)
    paid_at = models.DateTimeField(null=True, blank=True)
    amount_paid = models.DecimalField(max_digits=15, decimal_places=2, null=True, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'bills'

    def __str__(self):
        return f"{self.biller_name} — {self.amount}"


# ============================================================
# 6) LoginSession — جلسة تسجيل الدخول
# ============================================================
class LoginSession(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)

    client = models.ForeignKey(
        Client,
        on_delete=models.RESTRICT,
        related_name='login_sessions'
    )

    token_hash = models.TextField(unique=True)
    ip_address = models.GenericIPAddressField()
    user_agent = models.TextField(null=True, blank=True)
    device_info = models.TextField(null=True, blank=True)
    device_id = models.UUIDField(null=True, blank=True)

    expires_at = models.DateTimeField()
    is_active = models.BooleanField(default=True)
    revoked_at = models.DateTimeField(null=True, blank=True)
    revoke_reason = models.TextField(null=True, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'login_sessions'

    def __str__(self):
        return f"{self.client.username} — {self.created_at}"


# ============================================================
# 7) BankAuditLog — سجل التدقيق
# ============================================================
class BankAuditLog(models.Model):
    RESULT_CHOICES = [
        ('ok', 'OK'),
        ('fail', 'Fail'),
    ]

    id = models.BigAutoField(primary_key=True)
    client_id = models.UUIDField(null=True, blank=True)
    account_id = models.UUIDField(null=True, blank=True)

    action = models.TextField()
    result = models.CharField(max_length=10, choices=RESULT_CHOICES)

    failure_reason = models.TextField(null=True, blank=True)
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    user_agent = models.TextField(null=True, blank=True)
    metadata = models.JSONField(null=True, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'bank_audit_log'

    def __str__(self):
        return f"{self.action} — {self.result}"