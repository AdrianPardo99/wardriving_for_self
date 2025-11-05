-- Change Visual Mode to Cake graph
-- Copy Paste the name of Bi table in your metabase implementation
-- D02 - Quantity of auth type
SELECT
	auth_mode,
	count(*) as qty_auth
FROM wardriving
WHERE
	{{ssid}}
	AND {{bssid}}
	AND {{device_source}}
	AND {{author}}
	AND {{first_seen}}
	AND (current_latitude!=0 AND current_longitude!=0)
	AND deleted_at is NULL
GROUP BY auth_mode