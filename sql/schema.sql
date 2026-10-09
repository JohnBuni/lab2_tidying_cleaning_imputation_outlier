-- Neon project: lab2-tidying-cleaning-group
-- Database:     tidying_cleaning_imputation_outliers
-- Roles:        tidying_cleaning_owner (database owner)
--               tidying_cleaning_team  (shared by the team and the professor: read/write data, create tables)

-- Access for the shared team role
GRANT CONNECT, TEMP ON DATABASE tidying_cleaning_imputation_outliers TO tidying_cleaning_team;
GRANT USAGE, CREATE ON SCHEMA public TO tidying_cleaning_team;
ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT SELECT, INSERT, UPDATE, DELETE, TRUNCATE ON TABLES TO tidying_cleaning_team;
ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT USAGE, SELECT ON SEQUENCES TO tidying_cleaning_team;

-- Section 3 - Data Cleaning (Cars Dataset)
CREATE TABLE cars_raw (
    row_num integer PRIMARY KEY,   -- line order of data/cars.csv (row 1 = data-type labels)
    car text, mpg text, cylinders text, displacement text, horsepower text,
    weight text, acceleration text, model text, origin text
);
CREATE TABLE cars_public_epa (     -- 1,000-vehicle sample of the US EPA fuel economy file
    epa_id integer PRIMARY KEY, make text NOT NULL, model text NOT NULL, year integer NOT NULL,
    comb08 integer, cylinders numeric, displ numeric,
    fueltype1 text, atvtype text, trany text, vclass text
);
CREATE TABLE cars_clean (          -- written by CarsWorker.save_clean()
    car text, mpg double precision, cylinders double precision, displacement double precision,
    horsepower double precision, weight double precision, acceleration double precision,
    model integer, origin text, source text
);
