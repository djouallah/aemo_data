WITH
  duid_aemo AS MATERIALIZED (
    SELECT
      DUID AS DUID,
      first(Region) AS Region,
      first("Fuel Source - Descriptor") AS FuelSourceDescriptor,
      first(Participant) AS Participant
    FROM 'abfss://$ws@$storage_account.dfs.fabric.microsoft.com/$lh.Lakehouse/Files/raw/nem-registration-and-exemption-list_PU_and_Scheduled_Loads.csv',
    
    WHERE
      length(DUID) > 2
    GROUP BY
      DUID
  ),
  states AS (
    SELECT 'WA1' AS RegionID, 'Western Australia' AS States
    UNION ALL SELECT 'QLD1', 'Queensland'
    UNION ALL SELECT 'NSW1', 'New South Walles'
    UNION ALL SELECT 'TAS1', 'Tasmania'
    UNION ALL SELECT 'SA1', 'South Australia'
    UNION ALL SELECT 'VIC1', 'Victoria'
  ),
  x AS MATERIALIZED (
    SELECT
      'WA1' AS Region,
      "Facility Code" AS DUID,
      "Participant Name" AS Participant
    FROM read_csv('https://data.wa.aemo.com.au/datafiles/post-facilities/facilities.csv')
  ),
  tt AS MATERIALIZED (
    SELECT
      *
    FROM read_csv('https://raw.githubusercontent.com/djouallah/fabric_demo/refs/heads/main/data/duid/WA_ENERGY.csv')
  ),
  duid_wa AS (
    SELECT
      x.DUID,
      x.Region,
      Technology AS FuelSourceDescriptor,
      x.Participant
    FROM x
    LEFT JOIN tt ON x.DUID = tt.DUID
  ),
  duid_all AS (
    SELECT
      *
    FROM duid_aemo
    UNION ALL
    SELECT
      *
    FROM duid_wa
  ),
geo as MATERIALIZED (
  select duid, max(latitude) as latitude,max(longitude) as longitude from
  read_csv('https://raw.githubusercontent.com/djouallah/fabric_demo/refs/heads/main/data/duid/geo.csv')

  where latitude is not null
group by all)
SELECT
  distinct(a.DUID) as DUID,
  Region,
  UPPER(LEFT(TRIM(FuelSourceDescriptor), 1)) || LOWER(SUBSTR(TRIM(FuelSourceDescriptor), 2)) AS FuelSourceDescriptor,
  Participant,
  states.States AS State,
  geo.latitude,
  geo.longitude
FROM duid_all a
JOIN states ON a.Region = states.RegionID
left JOIN geo ON a.duid = geo.duid;
