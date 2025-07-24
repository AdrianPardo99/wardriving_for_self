-- Change Visual Mode to Map With pins in metabase 
-- Copy Paste the name of Bi table in your metabase implementation
-- D00 - Map related to analysis
SELECT
	mac,
	ssid,
	auth_mode,
	first_seen,
	channel,
	rssi,
	CASE
    	WHEN rssi > -50 THEN 'Excellent'
        WHEN rssi BETWEEN -60 AND -50 THEN 'Good'
        WHEN rssi BETWEEN -70 AND -60 THEN 'Fair'
        ELSE 'Weak'
	END AS signal_streng,
	device_source,
	uploaded_by,
	wardriving.type,
	current_latitude,
	current_longitude,
	altitude_meters,
	accuracy_meters
FROM wardriving
WHERE
	{{ssid}}
	AND {{device_source}}
	AND {{author}}
	AND {{first_seen}}
	AND (current_latitude!=0 AND current_longitude!=0)