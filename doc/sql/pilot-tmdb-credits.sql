-- open-credits pilot (OPEN-CREDITS-003): the TMDb credits of the pilot movies read so far, the reference for the OCR recall check.
-- Read-only. Add a movie ID to the two IN lists when the client reads a new pilot title.
-- Alien 348, Spirited Away 129, A Separation 60243.

-- 1. Counts per movie, credit type and department
SELECT pm.ID_MOVIE, pm.CREDIT_TYPE, pm.CREW_DEPARTMENT, COUNT(*) AS credits
FROM T_WC_TMDB_PERSON_MOVIE pm
WHERE pm.ID_MOVIE IN (348, 129, 60243) AND COALESCE(pm.DELETED, 0) = 0
GROUP BY pm.ID_MOVIE, pm.CREDIT_TYPE, pm.CREW_DEPARTMENT
ORDER BY pm.ID_MOVIE, pm.CREDIT_TYPE, credits DESC;

-- 2. Every credit, one line each (person, job or character), with the person's other names
--    (also known as: the names in other scripts, needed to match Japanese or Persian credits)
SELECT pm.ID_MOVIE, pm.CREDIT_TYPE, pm.DISPLAY_ORDER, pm.ID_PERSON, p.NAME, p.ID_IMDB,
       pm.CREW_DEPARTMENT, pm.CREW_JOB, pm.CAST_CHARACTER,
       (SELECT GROUP_CONCAT(a.PERSON_NAME ORDER BY a.PERSON_NAME SEPARATOR ' ; ')
          FROM T_WC_TMDB_PERSON_ALSO_KNOWN_AS a
         WHERE a.ID_PERSON = pm.ID_PERSON AND COALESCE(a.DELETED, 0) = 0) AS ALSO_KNOWN_AS
FROM T_WC_TMDB_PERSON_MOVIE pm
LEFT JOIN T_WC_TMDB_PERSON p ON p.ID_PERSON = pm.ID_PERSON
WHERE pm.ID_MOVIE IN (348, 129, 60243) AND COALESCE(pm.DELETED, 0) = 0
ORDER BY pm.ID_MOVIE, pm.CREDIT_TYPE, pm.CREW_DEPARTMENT, pm.CREW_JOB, pm.DISPLAY_ORDER, p.NAME;
