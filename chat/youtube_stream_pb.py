"""Minimal protobuf definitions for YouTube's official liveChatMessages.streamList RPC.

Field numbers and RPC name follow Google's published stream_list.proto. Only fields
needed by LlamaQueue's read-only chat viewer are included.
"""
from google.protobuf import descriptor_pb2, descriptor_pool, message_factory

_file = descriptor_pb2.FileDescriptorProto()
_file.name = "llamaqueue_stream_list.proto"
_file.package = "youtube.api.v3"
_file.syntax = "proto2"

F = descriptor_pb2.FieldDescriptorProto


def _message(name, fields):
    msg = _file.message_type.add()
    msg.name = name
    for field_name, number, field_type, label, type_name in fields:
        field = msg.field.add()
        field.name = field_name
        field.number = number
        field.type = field_type
        field.label = label
        if type_name:
            field.type_name = type_name


_optional = F.LABEL_OPTIONAL
_repeated = F.LABEL_REPEATED
_string = F.TYPE_STRING
_bool = F.TYPE_BOOL
_uint32 = F.TYPE_UINT32
_message_type = F.TYPE_MESSAGE

_message("LiveChatMessageListRequest", [
    ("live_chat_id", 1, _string, _optional, None),
    ("profile_image_size", 3, _uint32, _optional, None),
    ("page_token", 99, _string, _optional, None),
    ("part", 100, _string, _repeated, None),
])
_message("LiveChatTextMessageDetails", [
    ("message_text", 1, _string, _optional, None),
])
_message("LiveChatNewSponsorDetails", [
    ("member_level_name", 1, _string, _optional, None),
    ("is_upgrade", 2, _bool, _optional, None),
])
_message("LiveChatMemberMilestoneChatDetails", [
    ("member_level_name", 1, _string, _optional, None),
    ("member_month", 2, _uint32, _optional, None),
    ("user_comment", 3, _string, _optional, None),
])

_message("LiveChatSuperChatDetails", [
    ("amount_micros", 1, _string, _optional, None),
    ("currency", 2, _string, _optional, None),
    ("amount_display_string", 3, _string, _optional, None),
    ("user_comment", 4, _string, _optional, None),
])
_message("LiveChatMembershipGiftingDetails", [
    ("gift_memberships_count", 1, _uint32, _optional, None),
    ("gift_memberships_level_name", 2, _string, _optional, None),
])
_message("LiveChatGiftMembershipReceivedDetails", [
    ("member_level_name", 1, _string, _optional, None),
    ("gifter_channel_id", 2, _string, _optional, None),
    ("associated_membership_gifting_message_id", 3, _string, _optional, None),
])
_enum = _file.enum_type.add()
_enum.name = "LiveChatMessageSnippetType"
for enum_name, enum_number in [("INVALID_TYPE", 0), ("TEXT_MESSAGE_EVENT", 1), ("TOMBSTONE", 2), ("FAN_FUNDING_EVENT", 3), ("CHAT_ENDED_EVENT", 4), ("SPONSOR_ONLY_MODE_STARTED_EVENT", 5), ("SPONSOR_ONLY_MODE_ENDED_EVENT", 6), ("NEW_SPONSOR_EVENT", 7), ("MEMBER_MILESTONE_CHAT_EVENT", 17), ("MEMBERSHIP_GIFTING_EVENT", 18), ("GIFT_MEMBERSHIP_RECEIVED_EVENT", 19)]:
    value = _enum.value.add()
    value.name = enum_name
    value.number = enum_number

_message("LiveChatMessageSnippet", [
    ("type", 1, F.TYPE_ENUM, _optional, ".youtube.api.v3.LiveChatMessageSnippetType"),
    ("published_at", 4, _string, _optional, None),
    ("display_message", 16, _string, _optional, None),
    ("has_display_content", 17, _bool, _optional, None),
    ("text_message_details", 19, _message_type, _optional, ".youtube.api.v3.LiveChatTextMessageDetails"),
    ("new_sponsor_details", 29, _message_type, _optional, ".youtube.api.v3.LiveChatNewSponsorDetails"),
    ("member_milestone_chat_details", 30, _message_type, _optional, ".youtube.api.v3.LiveChatMemberMilestoneChatDetails"),
    ("super_chat_details", 27, _message_type, _optional, ".youtube.api.v3.LiveChatSuperChatDetails"),
    ("membership_gifting_details", 35, _message_type, _optional, ".youtube.api.v3.LiveChatMembershipGiftingDetails"),
    ("gift_membership_received_details", 36, _message_type, _optional, ".youtube.api.v3.LiveChatGiftMembershipReceivedDetails"),
])
_message("LiveChatMessageAuthorDetails", [
    ("channel_id", 10101, _string, _optional, None),
    ("display_name", 103, _string, _optional, None),
    ("profile_image_url", 104, _string, _optional, None),
    ("is_verified", 4, _bool, _optional, None),
    ("is_chat_moderator", 7, _bool, _optional, None),
    ("is_chat_owner", 5, _bool, _optional, None),
    ("is_chat_sponsor", 6, _bool, _optional, None),
])
_message("LiveChatMessage", [
    ("id", 101, _string, _optional, None),
    ("snippet", 2, _message_type, _optional, ".youtube.api.v3.LiveChatMessageSnippet"),
    ("author_details", 3, _message_type, _optional, ".youtube.api.v3.LiveChatMessageAuthorDetails"),
])
_message("LiveChatMessageListResponse", [
    ("next_page_token", 100602, _string, _optional, None),
    ("items", 1007, _message_type, _repeated, ".youtube.api.v3.LiveChatMessage"),
])

_service = _file.service.add()
_service.name = "V3DataLiveChatMessageService"
_method = _service.method.add()
_method.name = "StreamList"
_method.input_type = ".youtube.api.v3.LiveChatMessageListRequest"
_method.output_type = ".youtube.api.v3.LiveChatMessageListResponse"
_method.server_streaming = True

_pool = descriptor_pool.Default()
try:
    _pool.AddSerializedFile(_file.SerializeToString())
except Exception:
    pass


def _class(name):
    return message_factory.GetMessageClass(_pool.FindMessageTypeByName("youtube.api.v3." + name))


LiveChatMessageListRequest = _class("LiveChatMessageListRequest")
LiveChatMessageListResponse = _class("LiveChatMessageListResponse")
