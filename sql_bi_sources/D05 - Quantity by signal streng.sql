-- Change Visual Mode to Cake graph
-- Copy Paste the name of Bi table in your metabase implementation
-- D05 - Quantity by signal streng
SELECT
	CASE
    	WHEN rssi > -50 THEN 'Excellent'
        WHEN rssi BETWEEN -60 AND -50 THEN 'Good'
        WHEN rssi BETWEEN -70 AND -60 THEN 'Fair'
        ELSE 'Weak'
	END AS signal_streng,
	count(*) as qty_by_signal
FROM wardriving
WHERE
	{{ssid}}
	AND {{bssid}}
	AND {{device_source}}
	AND {{author}}
	AND {{first_seen}}
	AND (current_latitude!=0 AND current_longitude!=0)
	AND deleted_at is NULL
GROUP BY signal_streng