-- open-credits pilot (OPEN-CREDITS-003): the TMDb credits of one pilot movie, the reference for the OCR recall check.
-- Read-only. Change @ID_MOVIE to run it for another pilot title (Alien is 348).
SET @ID_MOVIE = 348;

-- 1. Counts per credit type and department
SELECT pm.CREDIT_TYPE, pm.CREW_DEPARTMENT, COUNT(*) AS credits
FROM T_WC_TMDB_PERSON_MOVIE pm
WHERE pm.ID_MOVIE = @ID_MOVIE AND COALESCE(pm.DELETED, 0) = 0
GROUP BY pm.CREDIT_TYPE, pm.CREW_DEPARTMENT
ORDER BY pm.CREDIT_TYPE, credits DESC;

-- 2. Every credit, one line each (person, job or character)
SELECT pm.CREDIT_TYPE, pm.DISPLAY_ORDER, pm.ID_PERSON, p.NAME, p.ID_IMDB,
       pm.CREW_DEPARTMENT, pm.CREW_JOB, pm.CAST_CHARACTER
FROM T_WC_TMDB_PERSON_MOVIE pm
LEFT JOIN T_WC_TMDB_PERSON p ON p.ID_PERSON = pm.ID_PERSON
WHERE pm.ID_MOVIE = @ID_MOVIE AND COALESCE(pm.DELETED, 0) = 0
ORDER BY pm.CREDIT_TYPE, pm.CREW_DEPARTMENT, pm.CREW_JOB, pm.DISPLAY_ORDER, p.NAME;
