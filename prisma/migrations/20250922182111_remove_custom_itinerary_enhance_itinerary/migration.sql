/*
  Warnings:

  - You are about to drop the `custom_itineraries` table. If the table is not empty, all the data it contains will be lost.

*/
-- DropForeignKey
ALTER TABLE "public"."custom_itineraries" DROP CONSTRAINT "custom_itineraries_cityId_fkey";

-- DropForeignKey
ALTER TABLE "public"."custom_itineraries" DROP CONSTRAINT "custom_itineraries_userId_fkey";

-- AlterTable
ALTER TABLE "public"."itineraries" ADD COLUMN     "accommodationBudgetPerNight" INTEGER,
ADD COLUMN     "accommodationType" TEXT,
ADD COLUMN     "budgetPerDay" INTEGER,
ADD COLUMN     "destination" TEXT,
ADD COLUMN     "endDate" TEXT,
ADD COLUMN     "interests" TEXT[],
ADD COLUMN     "safetyPriority" TEXT,
ADD COLUMN     "specialRequests" TEXT,
ADD COLUMN     "startDate" TEXT,
ADD COLUMN     "status" TEXT NOT NULL DEFAULT 'draft',
ADD COLUMN     "travelStyle" TEXT;

-- DropTable
DROP TABLE "public"."custom_itineraries";
