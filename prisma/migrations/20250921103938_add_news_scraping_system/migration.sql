/*
  Warnings:

  - The primary key for the `_QuestBadgeRewards` table will be changed. If it partially fails, the table could be left without primary key constraint.
  - The primary key for the `_UserFriends` table will be changed. If it partially fails, the table could be left without primary key constraint.
  - A unique constraint covering the columns `[A,B]` on the table `_QuestBadgeRewards` will be added. If there are existing duplicate values, this will fail.
  - A unique constraint covering the columns `[A,B]` on the table `_UserFriends` will be added. If there are existing duplicate values, this will fail.

*/
-- CreateEnum
CREATE TYPE "NewsSourceType" AS ENUM ('RSS', 'NEWSAPI', 'WEB_SCRAPE', 'MCP', 'LOCAL_NEWS');

-- CreateEnum
CREATE TYPE "NewsConcernType" AS ENUM ('CRIME', 'VIOLENCE', 'TERRORISM', 'TRAFFIC', 'NATURAL_DISASTER', 'HEALTH', 'INFRASTRUCTURE', 'POSITIVE', 'UNKNOWN');

-- CreateEnum
CREATE TYPE "NewsJobStatus" AS ENUM ('PENDING', 'RUNNING', 'COMPLETED', 'FAILED', 'CANCELLED');

-- AlterTable
ALTER TABLE "_QuestBadgeRewards" DROP CONSTRAINT "_QuestBadgeRewards_AB_pkey";

-- AlterTable
ALTER TABLE "_UserFriends" DROP CONSTRAINT "_UserFriends_AB_pkey";

-- CreateTable
CREATE TABLE "news_articles" (
    "id" TEXT NOT NULL,
    "title" TEXT NOT NULL,
    "summary" TEXT,
    "content" TEXT,
    "url" TEXT NOT NULL,
    "published" TIMESTAMP(3),
    "source" TEXT NOT NULL,
    "type" "NewsSourceType" NOT NULL DEFAULT 'RSS',
    "cityId" TEXT,
    "latitude" DOUBLE PRECISION,
    "longitude" DOUBLE PRECISION,
    "locationRadius" DOUBLE PRECISION,
    "safetyScore" DOUBLE PRECISION NOT NULL DEFAULT 0.0,
    "threatLevel" INTEGER NOT NULL DEFAULT 5,
    "concernType" "NewsConcernType" NOT NULL DEFAULT 'UNKNOWN',
    "sentimentPolarity" DOUBLE PRECISION NOT NULL DEFAULT 0.0,
    "sentimentSubjectivity" DOUBLE PRECISION NOT NULL DEFAULT 0.0,
    "confidence" DOUBLE PRECISION NOT NULL DEFAULT 0.0,
    "isProcessed" BOOLEAN NOT NULL DEFAULT false,
    "isRelevant" BOOLEAN NOT NULL DEFAULT false,
    "processedAt" TIMESTAMP(3),
    "createdAt" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,
    "updatedAt" TIMESTAMP(3) NOT NULL,

    CONSTRAINT "news_articles_pkey" PRIMARY KEY ("id")
);

-- CreateTable
CREATE TABLE "news_safety_impacts" (
    "id" TEXT NOT NULL,
    "newsArticleId" TEXT NOT NULL,
    "cityId" TEXT NOT NULL,
    "impactFactor" DOUBLE PRECISION NOT NULL DEFAULT 0.0,
    "weightFactor" DOUBLE PRECISION NOT NULL DEFAULT 1.0,
    "decayFactor" DOUBLE PRECISION NOT NULL DEFAULT 1.0,
    "latitude" DOUBLE PRECISION NOT NULL,
    "longitude" DOUBLE PRECISION NOT NULL,
    "radiusKm" DOUBLE PRECISION NOT NULL DEFAULT 5.0,
    "isActive" BOOLEAN NOT NULL DEFAULT true,
    "expiresAt" TIMESTAMP(3),
    "createdAt" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT "news_safety_impacts_pkey" PRIMARY KEY ("id")
);

-- CreateTable
CREATE TABLE "news_scraping_jobs" (
    "id" TEXT NOT NULL,
    "cityId" TEXT,
    "status" "NewsJobStatus" NOT NULL DEFAULT 'PENDING',
    "latitude" DOUBLE PRECISION,
    "longitude" DOUBLE PRECISION,
    "radiusKm" DOUBLE PRECISION NOT NULL DEFAULT 50.0,
    "daysBack" INTEGER NOT NULL DEFAULT 7,
    "sources" TEXT[],
    "articlesFound" INTEGER NOT NULL DEFAULT 0,
    "articlesProcessed" INTEGER NOT NULL DEFAULT 0,
    "safetyRelevant" INTEGER NOT NULL DEFAULT 0,
    "startedAt" TIMESTAMP(3),
    "completedAt" TIMESTAMP(3),
    "errorMessage" TEXT,
    "createdAt" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT "news_scraping_jobs_pkey" PRIMARY KEY ("id")
);

-- CreateIndex
CREATE UNIQUE INDEX "news_articles_url_key" ON "news_articles"("url");

-- CreateIndex
CREATE UNIQUE INDEX "_QuestBadgeRewards_AB_unique" ON "_QuestBadgeRewards"("A", "B");

-- CreateIndex
CREATE UNIQUE INDEX "_UserFriends_AB_unique" ON "_UserFriends"("A", "B");

-- AddForeignKey
ALTER TABLE "news_articles" ADD CONSTRAINT "news_articles_cityId_fkey" FOREIGN KEY ("cityId") REFERENCES "cities"("id") ON DELETE SET NULL ON UPDATE CASCADE;

-- AddForeignKey
ALTER TABLE "news_safety_impacts" ADD CONSTRAINT "news_safety_impacts_newsArticleId_fkey" FOREIGN KEY ("newsArticleId") REFERENCES "news_articles"("id") ON DELETE CASCADE ON UPDATE CASCADE;

-- AddForeignKey
ALTER TABLE "news_safety_impacts" ADD CONSTRAINT "news_safety_impacts_cityId_fkey" FOREIGN KEY ("cityId") REFERENCES "cities"("id") ON DELETE RESTRICT ON UPDATE CASCADE;

-- AddForeignKey
ALTER TABLE "news_scraping_jobs" ADD CONSTRAINT "news_scraping_jobs_cityId_fkey" FOREIGN KEY ("cityId") REFERENCES "cities"("id") ON DELETE SET NULL ON UPDATE CASCADE;
