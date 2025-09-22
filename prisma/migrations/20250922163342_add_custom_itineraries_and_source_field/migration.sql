-- CreateEnum
CREATE TYPE "public"."ItinerarySource" AS ENUM ('AI', 'USER');

-- AlterTable
ALTER TABLE "public"."_QuestBadgeRewards" ADD CONSTRAINT "_QuestBadgeRewards_AB_pkey" PRIMARY KEY ("A", "B");

-- DropIndex
DROP INDEX "public"."_QuestBadgeRewards_AB_unique";

-- AlterTable
ALTER TABLE "public"."_UserFriends" ADD CONSTRAINT "_UserFriends_AB_pkey" PRIMARY KEY ("A", "B");

-- DropIndex
DROP INDEX "public"."_UserFriends_AB_unique";

-- AlterTable
ALTER TABLE "public"."itineraries" ADD COLUMN     "source" "public"."ItinerarySource" NOT NULL DEFAULT 'AI';

-- CreateTable
CREATE TABLE "public"."custom_itineraries" (
    "id" TEXT NOT NULL,
    "userId" TEXT NOT NULL,
    "title" TEXT NOT NULL,
    "destination" TEXT NOT NULL,
    "startDate" TEXT NOT NULL,
    "endDate" TEXT NOT NULL,
    "budgetPerDay" INTEGER,
    "travelStyle" TEXT NOT NULL,
    "interests" TEXT[],
    "accommodationType" TEXT NOT NULL,
    "accommodationBudgetPerNight" INTEGER,
    "safetyPriority" TEXT NOT NULL,
    "specialRequests" TEXT,
    "cityId" TEXT,
    "status" TEXT NOT NULL DEFAULT 'draft',
    "isActive" BOOLEAN NOT NULL DEFAULT true,
    "createdAt" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,
    "updatedAt" TIMESTAMP(3) NOT NULL,

    CONSTRAINT "custom_itineraries_pkey" PRIMARY KEY ("id")
);

-- AddForeignKey
ALTER TABLE "public"."custom_itineraries" ADD CONSTRAINT "custom_itineraries_userId_fkey" FOREIGN KEY ("userId") REFERENCES "public"."users"("id") ON DELETE RESTRICT ON UPDATE CASCADE;

-- AddForeignKey
ALTER TABLE "public"."custom_itineraries" ADD CONSTRAINT "custom_itineraries_cityId_fkey" FOREIGN KEY ("cityId") REFERENCES "public"."cities"("id") ON DELETE SET NULL ON UPDATE CASCADE;
