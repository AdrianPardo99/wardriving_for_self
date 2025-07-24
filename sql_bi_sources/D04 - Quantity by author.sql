-- Change Visual Mode to Cake graph
-- Copy Paste the name of Bi table in your metabase implementation
-- D04 - Quantity by author
SELECT
	uploaded_by,
	count(*) as qty_by_author
FROM wardriving
WHERE
	{{ssid}}
	AND {{device_source}}
	AND {{author}}
	AND {{first_seen}}
	AND (current_latitude!=0 AND current_longitude!=0)
GROUP BY uploaded_by