-- Change Visual Mode to Map With pins in metabase 
-- Copy Paste the name of Bi table in your metabase implementation
-- D00 - Map related to analysis
SELECT
	wardriving.mac,	
	--vendor.registry ,
	vendor.organization_name as vendor,
	vendor.source,
	wardriving.ssid,
	wardriving.auth_mode,
	wardriving.first_seen,
	wardriving.channel,
	wardriving.rssi,
	CASE
    	WHEN wardriving.rssi > -50 THEN 'Excellent'
        WHEN wardriving.rssi BETWEEN -60 AND -50 THEN 'Good'
        WHEN wardriving.rssi BETWEEN -70 AND -60 THEN 'Fair'
        ELSE 'Weak'
	END AS signal_streng,
	wardriving.device_source,
	wardriving.uploaded_by,
	wardriving.type,
	wardriving.current_latitude,
	wardriving.current_longitude,
	wardriving.altitude_meters,
	wardriving.accuracy_meters
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