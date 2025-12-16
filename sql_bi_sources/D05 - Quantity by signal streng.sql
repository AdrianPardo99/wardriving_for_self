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
LEFT JOIN vendor ON REGEXP_REPLACE(vendor.normalized_prefix,'(.{2})(.{2})(.{2})', '\1:\2:\3')=SUBSTRING(wardriving.mac,1,8)
WHERE
	{{ssid}}
	AND {{device_source}}
	AND {{author}}
	AND {{first_seen}}
	AND {{bssid}}
	AND {{auth_mode}}
	AND {{vendor}}
	AND (current_latitude!=0 AND current_longitude!=0)
	AND wardriving.deleted_at is NULL
GROUP BY signal_streng