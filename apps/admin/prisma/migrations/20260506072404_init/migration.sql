-- CreateTable
CREATE TABLE "staff_users" (
    "id" TEXT NOT NULL,
    "email" TEXT NOT NULL,
    "password_hash" TEXT NOT NULL,
    "name" TEXT NOT NULL,
    "role" TEXT NOT NULL DEFAULT 'therapist',
    "therapist_id" TEXT,
    "created_at" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,
    "updated_at" TIMESTAMP(3) NOT NULL,

    CONSTRAINT "staff_users_pkey" PRIMARY KEY ("id")
);

-- CreateTable
CREATE TABLE "therapists" (
    "id" TEXT NOT NULL,
    "name" TEXT NOT NULL,
    "commission_rate" DOUBLE PRECISION NOT NULL DEFAULT 0.8,
    "is_active" BOOLEAN NOT NULL DEFAULT true,
    "bio" TEXT,
    "specialties" TEXT,
    "created_at" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,
    "updated_at" TIMESTAMP(3) NOT NULL,

    CONSTRAINT "therapists_pkey" PRIMARY KEY ("id")
);

-- CreateTable
CREATE TABLE "therapist_availability" (
    "id" TEXT NOT NULL,
    "therapist_id" TEXT NOT NULL,
    "day_of_week" INTEGER NOT NULL,
    "start_time" TEXT NOT NULL,
    "end_time" TEXT NOT NULL,
    "is_recurring" BOOLEAN NOT NULL DEFAULT true,
    "effective_from" TIMESTAMP(3),
    "effective_until" TIMESTAMP(3),
    "created_at" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT "therapist_availability_pkey" PRIMARY KEY ("id")
);

-- CreateTable
CREATE TABLE "clients" (
    "id" TEXT NOT NULL,
    "name" TEXT NOT NULL,
    "phone" TEXT,
    "email" TEXT,
    "booking_client_user_id" TEXT,
    "notes" TEXT,
    "created_at" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,
    "updated_at" TIMESTAMP(3) NOT NULL,

    CONSTRAINT "clients_pkey" PRIMARY KEY ("id")
);

-- CreateTable
CREATE TABLE "sessions" (
    "id" TEXT NOT NULL,
    "date" TIMESTAMP(3) NOT NULL,
    "room" TEXT,
    "therapist_id" TEXT NOT NULL,
    "client_id" TEXT NOT NULL,
    "source" TEXT NOT NULL DEFAULT 'manual',
    "booking_appointment_id" TEXT,
    "billing_type" TEXT,
    "amount_receivable" DOUBLE PRECISION,
    "receivable_type" TEXT,
    "location" TEXT,
    "payment_status" TEXT,
    "amount_received" DOUBLE PRECISION,
    "institution_month" TEXT,
    "counseling_format" TEXT,
    "counseling_type" TEXT,
    "hours" DOUBLE PRECISION,
    "hourly_rate" DOUBLE PRECISION,
    "total_fee" DOUBLE PRECISION,
    "commission_rate" DOUBLE PRECISION,
    "therapist_income" DOUBLE PRECISION,
    "clinic_income" DOUBLE PRECISION,
    "notes" TEXT,
    "therapist_paid" TEXT,
    "created_at" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,
    "updated_at" TIMESTAMP(3) NOT NULL,

    CONSTRAINT "sessions_pkey" PRIMARY KEY ("id")
);

-- CreateTable
CREATE TABLE "import_logs" (
    "id" TEXT NOT NULL,
    "filename" TEXT NOT NULL,
    "rows_imported" INTEGER NOT NULL,
    "imported_by" TEXT NOT NULL,
    "imported_at" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT "import_logs_pkey" PRIMARY KEY ("id")
);

-- CreateIndex
CREATE UNIQUE INDEX "staff_users_email_key" ON "staff_users"("email");

-- CreateIndex
CREATE UNIQUE INDEX "therapists_name_key" ON "therapists"("name");

-- AddForeignKey
ALTER TABLE "staff_users" ADD CONSTRAINT "staff_users_therapist_id_fkey" FOREIGN KEY ("therapist_id") REFERENCES "therapists"("id") ON DELETE SET NULL ON UPDATE CASCADE;

-- AddForeignKey
ALTER TABLE "therapist_availability" ADD CONSTRAINT "therapist_availability_therapist_id_fkey" FOREIGN KEY ("therapist_id") REFERENCES "therapists"("id") ON DELETE RESTRICT ON UPDATE CASCADE;

-- AddForeignKey
ALTER TABLE "sessions" ADD CONSTRAINT "sessions_therapist_id_fkey" FOREIGN KEY ("therapist_id") REFERENCES "therapists"("id") ON DELETE RESTRICT ON UPDATE CASCADE;

-- AddForeignKey
ALTER TABLE "sessions" ADD CONSTRAINT "sessions_client_id_fkey" FOREIGN KEY ("client_id") REFERENCES "clients"("id") ON DELETE RESTRICT ON UPDATE CASCADE;

-- AddForeignKey
ALTER TABLE "import_logs" ADD CONSTRAINT "import_logs_imported_by_fkey" FOREIGN KEY ("imported_by") REFERENCES "staff_users"("id") ON DELETE RESTRICT ON UPDATE CASCADE;
