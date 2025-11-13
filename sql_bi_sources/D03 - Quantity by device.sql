-- Change Visual Mode to Cake graph
-- Copy Paste the name of Bi table in your metabase implementation
-- D03 - Quantity by device
SELECT
	device_source,
	count(*) as qty_device
FROM wardriving
WHERE
	{{ssid}}
	AND {{bssid}}
	AND {{device_source}}
	AND {{author}}
	AND {{first_seen}}
	AND {{auth_mode}}
	AND (current_latitude!=0 AND current_longitude!=0)
	AND deleted_at is NULL
GROUP BY device_source