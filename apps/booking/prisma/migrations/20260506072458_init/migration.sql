-- CreateTable
CREATE TABLE "client_users" (
    "id" TEXT NOT NULL,
    "email" TEXT NOT NULL,
    "password_hash" TEXT NOT NULL,
    "name" TEXT NOT NULL,
    "phone" TEXT,
    "created_at" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,
    "last_login" TIMESTAMP(3),

    CONSTRAINT "client_users_pkey" PRIMARY KEY ("id")
);

-- CreateTable
CREATE TABLE "therapist_profiles" (
    "id" TEXT NOT NULL,
    "name" TEXT NOT NULL,
    "bio" TEXT,
    "specialties" TEXT,
    "photo_url" TEXT,
    "is_accepting_bookings" BOOLEAN NOT NULL DEFAULT true,
    "internal_therapist_id" TEXT,
    "created_at" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,
    "updated_at" TIMESTAMP(3) NOT NULL,

    CONSTRAINT "therapist_profiles_pkey" PRIMARY KEY ("id")
);

-- CreateTable
CREATE TABLE "therapist_availability" (
    "id" TEXT NOT NULL,
    "therapist_profile_id" TEXT NOT NULL,
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
CREATE TABLE "appointments" (
    "id" TEXT NOT NULL,
    "client_user_id" TEXT NOT NULL,
    "therapist_profile_id" TEXT,
    "requested_date" TIMESTAMP(3) NOT NULL,
    "requested_time_slot" TEXT NOT NULL,
    "preferred_format" TEXT NOT NULL DEFAULT 'in_person',
    "client_name" TEXT NOT NULL,
    "client_phone" TEXT,
    "client_email" TEXT,
    "status" TEXT NOT NULL DEFAULT 'pending',
    "rejection_reason" TEXT,
    "notes" TEXT,
    "created_at" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,
    "updated_at" TIMESTAMP(3) NOT NULL,

    CONSTRAINT "appointments_pkey" PRIMARY KEY ("id")
);

-- CreateIndex
CREATE UNIQUE INDEX "client_users_email_key" ON "client_users"("email");

-- CreateIndex
CREATE UNIQUE INDEX "therapist_profiles_internal_therapist_id_key" ON "therapist_profiles"("internal_therapist_id");

-- AddForeignKey
ALTER TABLE "therapist_availability" ADD CONSTRAINT "therapist_availability_therapist_profile_id_fkey" FOREIGN KEY ("therapist_profile_id") REFERENCES "therapist_profiles"("id") ON DELETE CASCADE ON UPDATE CASCADE;

-- AddForeignKey
ALTER TABLE "appointments" ADD CONSTRAINT "appointments_client_user_id_fkey" FOREIGN KEY ("client_user_id") REFERENCES "client_users"("id") ON DELETE RESTRICT ON UPDATE CASCADE;

-- AddForeignKey
ALTER TABLE "appointments" ADD CONSTRAINT "appointments_therapist_profile_id_fkey" FOREIGN KEY ("therapist_profile_id") REFERENCES "therapist_profiles"("id") ON DELETE SET NULL ON UPDATE CASCADE;
