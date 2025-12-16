-- Change Visual Mode to Cake graph
-- Copy Paste the name of Bi table in your metabase implementation
-- D03 - Quantity by device
SELECT
	device_source,
	count(*) as qty_device
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
GROUP BY device_source