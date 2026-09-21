-- Analysis date range on protocol header
ALTER TABLE sample_protocols
    ADD COLUMN IF NOT EXISTS date_of_analysis_from DATE,
    ADD COLUMN IF NOT EXISTS date_of_analysis_to DATE;

UPDATE sample_protocols
   SET date_of_analysis_from = date_of_analysis,
       date_of_analysis_to = date_of_analysis
 WHERE date_of_analysis IS NOT NULL
   AND date_of_analysis_from IS NULL;
