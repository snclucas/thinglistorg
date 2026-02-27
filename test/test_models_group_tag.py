"""
Unit tests for Group, GroupMember, and Tag models.
"""
import pytest
from models import Group, GroupMember, Tag, db


class TestGroupModel:
    """Test Group model."""

    def test_group_creation(self, test_group):
        """Test creating a new group."""
        assert test_group.id is not None
        assert test_group.name == 'Test Group'
        assert test_group.owner_id is not None

    def test_group_to_dict(self, test_group):
        """Test group to_dict serialization."""
        group_dict = test_group.to_dict()

        assert group_dict['id'] == test_group.id
        assert group_dict['name'] == 'Test Group'
        assert group_dict['owner_id'] is not None
        assert 'created_at' in group_dict

    def test_group_repr(self, test_group):
        """Test group string representation."""
        assert str(test_group) == '<Group Test Group>'

    def test_group_get_default_settings(self, test_group):
        """Test default group settings."""
        settings = test_group.get_default_settings()

        assert 'allow_members_create_lists' in settings
        assert 'allow_members_edit_shared_lists' in settings
        assert 'default_member_role' in settings

    def test_group_get_settings_with_defaults(self, test_group):
        """Test getting settings applies defaults."""
        settings = test_group.get_settings()

        assert settings['allow_members_create_lists'] is True
        assert settings['default_member_role'] == 'member'

    def test_group_set_settings(self, test_group, db):
        """Test setting group settings."""
        new_settings = {
            'allow_members_create_lists': False,
            'allow_members_edit_shared_lists': True
        }
        test_group.set_settings(new_settings)
        db.commit()

        settings = test_group.get_settings()
        assert settings['allow_members_create_lists'] is False

    def test_group_is_owner(self, test_group, test_user, test_user2):
        """Test is_owner method."""
        assert test_group.is_owner(test_user.id) is True
        assert test_group.is_owner(test_user2.id) is False

    def test_group_is_admin_as_owner(self, test_group, test_user):
        """Test that owner is admin."""
        assert test_group.is_admin(test_user.id) is True

    def test_group_add_member(self, test_group, test_user2, db):
        """Test adding a member to group."""
        member = test_group.add_member(test_user2.id, role='member')
        db.commit()

        assert member.group_id == test_group.id
        assert member.user_id == test_user2.id
        assert member.role == 'member'

    def test_group_add_member_duplicate(self, test_group, test_user2, db):
        """Test adding duplicate member returns existing."""
        member1 = test_group.add_member(test_user2.id, role='member')
        db.commit()

        member2 = test_group.add_member(test_user2.id, role='admin')
        assert member1.id == member2.id

    def test_group_get_member(self, test_group, test_user2, db):
        """Test getting a specific member."""
        test_group.add_member(test_user2.id, role='member')
        db.commit()

        member = test_group.get_member(test_user2.id)
        assert member is not None
        assert member.user_id == test_user2.id

    def test_group_remove_member(self, test_group, test_user2, db):
        """Test removing a member from group."""
        test_group.add_member(test_user2.id)
        db.commit()

        success = test_group.remove_member(test_user2.id)
        db.commit()

        assert success is True
        member = test_group.get_member(test_user2.id)
        assert member is None

    def test_group_remove_member_not_exists(self, test_group, test_user2):
        """Test removing non-existent member."""
        success = test_group.remove_member(test_user2.id)
        assert success is False

    def test_group_get_members(self, test_group, test_user2, db):
        """Test getting all group members."""
        test_group.add_member(test_user2.id)
        db.commit()

        members = test_group.get_members()
        assert len(members) >= 1
        assert members[0].user_id == test_user2.id

    def test_group_user_has_role(self, test_group, test_user, test_user2, db):
        """Test checking user role."""
        assert test_group.user_has_role(test_user.id, 'owner') is True

        test_group.add_member(test_user2.id, role='member')
        db.commit()

        assert test_group.user_has_role(test_user2.id, 'member') is True
        assert test_group.user_has_role(test_user2.id, 'admin') is False


class TestGroupMember:
    """Test GroupMember model."""

    def test_group_member_creation(self, test_group, test_user2, db):
        """Test creating a group member."""
        member = GroupMember(
            group_id=test_group.id,
            user_id=test_user2.id,
            role='member'
        )
        db.add(member)
        db.commit()

        assert member.id is not None
        assert member.role == 'member'

    def test_group_member_repr(self, test_group, test_user2, db):
        """Test group member string representation."""
        member = GroupMember(
            group_id=test_group.id,
            user_id=test_user2.id,
            role='member'
        )
        db.add(member)
        db.commit()

        assert 'member' in str(member)

    def test_group_member_can_view(self, test_group, test_user2, db):
        """Test view permission for different roles."""
        member = GroupMember(
            group_id=test_group.id,
            user_id=test_user2.id,
            role='member'
        )
        db.add(member)
        db.commit()

        assert member.can_view() is True

    def test_group_member_can_edit_member_role(self, test_group, test_user2, db):
        """Test edit permission for member role."""
        member = GroupMember(
            group_id=test_group.id,
            user_id=test_user2.id,
            role='member'
        )
        db.add(member)
        db.commit()

        assert member.can_edit() is True

    def test_group_member_can_manage_admin(self, test_group, test_user2, db):
        """Test admin permission."""
        member = GroupMember(
            group_id=test_group.id,
            user_id=test_user2.id,
            role='admin'
        )
        db.add(member)
        db.commit()

        assert member.can_manage() is True

    def test_group_member_cannot_manage_viewer(self, test_group, test_user2, db):
        """Test viewer cannot manage."""
        member = GroupMember(
            group_id=test_group.id,
            user_id=test_user2.id,
            role='viewer'
        )
        db.add(member)
        db.commit()

        assert member.can_manage() is False

    def test_group_member_has_permission(self, test_group, test_user2, db):
        """Test checking specific permission."""
        member = GroupMember(
            group_id=test_group.id,
            user_id=test_user2.id,
            role='member'
        )
        db.add(member)
        db.commit()

        assert member.has_permission('view_lists') is True
        assert member.has_permission('create_lists') is True
        assert member.has_permission('edit_lists') is True

    def test_group_member_viewer_permissions(self, test_group, test_user2, db):
        """Test viewer role permissions."""
        member = GroupMember(
            group_id=test_group.id,
            user_id=test_user2.id,
            role='viewer'
        )
        db.add(member)
        db.commit()

        assert member.has_permission('view_lists') is True
        assert member.has_permission('edit_lists') is False

    def test_group_member_admin_has_all_permissions(self, test_group, test_user2, db):
        """Test that admin has all permissions."""
        member = GroupMember(
            group_id=test_group.id,
            user_id=test_user2.id,
            role='admin'
        )
        db.add(member)
        db.commit()

        assert member.has_permission('view_lists') is True
        assert member.has_permission('edit_lists') is True
        assert member.has_permission('delete_lists') is True


class TestTagModel:
    """Test Tag model."""

    def test_tag_creation(self, test_user, db):
        """Test creating a tag."""
        tag = Tag(name='important', user_id=test_user.id)
        db.add(tag)
        db.commit()

        assert tag.id is not None
        assert tag.name == 'important'
        assert tag.user_id == test_user.id

    def test_tag_repr(self, test_user, db):
        """Test tag string representation."""
        tag = Tag(name='urgent', user_id=test_user.id)
        db.add(tag)
        db.commit()

        assert str(tag) == '<Tag urgent>'

    def test_tag_normalize_tags(self):
        """Test normalize_tags static method."""
        tags_list = ['Tag1', ' tag2 ', 'TAG3', '  ', 'tag1']
        normalized = Tag.normalize_tags(tags_list)

        assert len(normalized) == 3  # Deduplicated
        assert 'tag1' in normalized
        assert 'tag2' in normalized
        assert 'tag3' in normalized

    def test_tag_normalize_tags_empty(self):
        """Test normalize_tags with empty input."""
        normalized = Tag.normalize_tags([])
        assert len(normalized) == 0

        normalized = Tag.normalize_tags(['', '  ', None])
        assert len(normalized) == 0

    def test_tag_get_or_create_many_new(self, test_user, db):
        """Test get_or_create_many with new tags."""
        tags_list = ['tag1', 'tag2', 'tag3']
        tags = Tag.get_or_create_many(tags_list, test_user.id)
        db.commit()

        assert len(tags) == 3
        names = [t.name for t in tags]
        assert 'tag1' in names

    def test_tag_get_or_create_many_existing(self, test_user, db):
        """Test get_or_create_many with existing tags."""
        # Create first tag
        tag1 = Tag(name='tag1', user_id=test_user.id)
        db.add(tag1)
        db.commit()

        # Try to create again
        tags = Tag.get_or_create_many(['tag1', 'tag2'], test_user.id)
        db.commit()

        assert len(tags) == 2
        # First tag should be the existing one
        assert tags[0].id == tag1.id

    def test_tag_get_or_create_many_empty(self, test_user):
        """Test get_or_create_many with empty list."""
        tags = Tag.get_or_create_many([], test_user.id)
        assert len(tags) == 0

