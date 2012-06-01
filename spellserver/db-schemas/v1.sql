CREATE TABLE `version`
(
 `version` INTEGER -- contains one row, set to 1
);

CREATE TABLE `node` -- contains one row
(
 `webport` STRING,
 `pubkey` STRING, -- "pk0-base32..", nacl public key
 `privkey` STRING -- "sk0-base32..", nacl private key
);

CREATE TABLE `webui_initial_nonces`
(
 `nonce` STRING
);

CREATE TABLE `webui_access_tokens`
(
 `token` STRING
);

CREATE TABLE `outbound_msgnums`
(
 `to_vatid` STRING, -- "pk0-base32.."
 `next_msgnum` INTEGER -- one higher than last ACKed message
);

CREATE TABLE `outbound_messages` -- unACKed messages
(
 `to_vatid` STRING, -- "pk0-base32.."
 `msgnum` INTEGER,
 `message` STRING
);

CREATE TABLE `inbound_msgnums`
(
 `from_vatid` STRING, -- "pk0-base32.."
 `next_msgnum` INTEGER -- one higher than last checkpointed message
);
