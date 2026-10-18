-- open-credits pilot: precision of the new lines per sample (charter, decision 27 c), from T_WC_OC_REVIEW.
-- SELECT only: ssh vps-agent run open-credits/doc/sql/oc-review-score.sql

SELECT SAMPLE, ID_MOVIE, COUNT(*) AS LINES_SAMPLED, COUNT(VERDICT) AS JUDGED,
       SUM(VERDICT = 'exact') AS EXACT, SUM(VERDICT = 'minor') AS MINOR,
       SUM(VERDICT = 'wrong') AS WRONG, SUM(VERDICT = 'noise') AS NOISE,
       ROUND(100 * SUM(VERDICT = 'exact') / NULLIF(COUNT(VERDICT), 0)) AS PCT_EXACT,
       ROUND(100 * SUM(VERDICT IN ('exact', 'minor')) / NULLIF(COUNT(VERDICT), 0)) AS PCT_EXACT_OR_MINOR,
       MAX(TIM_UPDATED) AS LAST_VERDICT
FROM T_WC_OC_REVIEW
WHERE DELETED = 0
GROUP BY SAMPLE, ID_MOVIE
ORDER BY SAMPLE;

-- the misses, with what the screen shows
SELECT SAMPLE, ITEM, VERDICT, LINE_TEXT, NOTE, LINE_KIND, WINDOW_NAME, FRAME_T
FROM T_WC_OC_REVIEW
WHERE DELETED = 0 AND VERDICT IS NOT NULL AND VERDICT <> 'exact'
ORDER BY SAMPLE, ITEM;
