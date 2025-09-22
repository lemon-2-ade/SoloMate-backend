-- AlterEnum
ALTER TYPE "public"."AiRecommendationType" ADD VALUE 'ITINERARY';

-- AlterTable
ALTER TABLE "public"."_QuestBadgeRewards" ADD CONSTRAINT "_QuestBadgeRewards_AB_pkey" PRIMARY KEY ("A", "B");

-- DropIndex
DROP INDEX "public"."_QuestBadgeRewards_AB_unique";

-- AlterTable
ALTER TABLE "public"."_UserFriends" ADD CONSTRAINT "_UserFriends_AB_pkey" PRIMARY KEY ("A", "B");

-- DropIndex
DROP INDEX "public"."_UserFriends_AB_unique";

-- CreateTable
CREATE TABLE "public"."itineraries" (
    "id" TEXT NOT NULL,
    "userId" TEXT NOT NULL,
    "cityId" TEXT,
    "title" TEXT NOT NULL,
    "date" TEXT NOT NULL,
    "cityName" TEXT NOT NULL,
    "timeSlots" JSONB NOT NULL,
    "totalEstimatedTime" TEXT NOT NULL,
    "safetyNotes" TEXT[],
    "weather" JSONB,
    "preferences" JSONB,
    "aiContext" JSONB,
    "questsGenerated" INTEGER NOT NULL DEFAULT 0,
    "isActive" BOOLEAN NOT NULL DEFAULT true,
    "createdAt" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,
    "updatedAt" TIMESTAMP(3) NOT NULL,

    CONSTRAINT "itineraries_pkey" PRIMARY KEY ("id")
);

-- AddForeignKey
ALTER TABLE "public"."itineraries" ADD CONSTRAINT "itineraries_userId_fkey" FOREIGN KEY ("userId") REFERENCES "public"."users"("id") ON DELETE RESTRICT ON UPDATE CASCADE;

-- AddForeignKey
ALTER TABLE "public"."itineraries" ADD CONSTRAINT "itineraries_cityId_fkey" FOREIGN KEY ("cityId") REFERENCES "public"."cities"("id") ON DELETE SET NULL ON UPDATE CASCADE;
