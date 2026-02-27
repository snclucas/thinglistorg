"""
Unit tests for List and Item models.
"""
import pytest
from models import List, Item, ListShare, ListCustomField, ItemCustomField, db


class TestListModel:
    """Test List model."""

    def test_list_creation(self, test_list):
        """Test creating a new list."""
        assert test_list.id is not None
        assert test_list.name == 'Test List'
        assert test_list.user_id is not None
        assert test_list.visibility == 'private'

    def test_list_to_dict(self, test_list):
        """Test list to_dict serialization."""
        list_dict = test_list.to_dict()

        assert list_dict['id'] == test_list.id
        assert list_dict['name'] == 'Test List'
        assert list_dict['visibility'] == 'private'
        assert 'created_at' in list_dict

    def test_list_repr(self, test_list):
        """Test list string representation."""
        assert str(test_list) == '<List Test List>'

    def test_list_is_private(self, test_list):
        """Test is_private method."""
        test_list.visibility = 'private'
        assert test_list.is_private() is True

    def test_list_is_public(self, test_list):
        """Test is_public method."""
        test_list.visibility = 'public'
        assert test_list.is_public() is True

    def test_list_is_hidden(self, test_list):
        """Test is_hidden method."""
        test_list.visibility = 'hidden'
        assert test_list.is_hidden() is True

    def test_list_is_publicly_accessible(self, test_list):
        """Test is_publicly_accessible method."""
        test_list.visibility = 'public'
        assert test_list.is_publicly_accessible() is True

        test_list.visibility = 'hidden'
        assert test_list.is_publicly_accessible() is True

        test_list.visibility = 'private'
        assert test_list.is_publicly_accessible() is False

    def test_list_owner_can_access(self, test_list, test_user):
        """Test that owner can access list."""
        assert test_list.user_can_access(test_user.id) is True

    def test_list_owner_can_edit(self, test_list, test_user):
        """Test that owner can edit list."""
        assert test_list.user_can_edit(test_user.id) is True

    def test_list_non_owner_cannot_access_private(self, test_list, test_user2):
        """Test that non-owner cannot access private list."""
        test_list.visibility = 'private'
        assert test_list.user_can_access(test_user2.id) is False

    def test_list_get_tags_list_empty(self, test_list):
        """Test getting tags list when empty."""
        tags = test_list.get_tags_list()
        assert len(tags) == 0

    def test_list_set_tags_list(self, test_list, db):
        """Test setting tags list."""
        test_list.set_tags_list(['tag1', 'tag2', 'tag3'])
        db.commit()

        tags = test_list.get_tags_list()
        assert len(tags) == 3
        assert 'tag1' in tags

    def test_list_default_field_settings(self):
        """Test default field settings."""
        defaults = List.get_default_field_settings()

        assert 'name' in defaults
        assert defaults['name']['visible'] is True
        assert defaults['name']['editable'] is True
        assert 'description' in defaults
        assert 'quantity' in defaults

    def test_list_get_field_settings(self, test_list):
        """Test getting field settings."""
        settings = test_list.get_field_settings()

        assert isinstance(settings, dict)
        assert 'name' in settings
        assert settings['name']['visible'] is True

    def test_list_set_field_settings(self, test_list, db):
        """Test setting field settings."""
        field_settings = {
            'name': {'visible': True, 'editable': True},
            'quantity': {'visible': False, 'editable': False}
        }
        test_list.set_field_settings(field_settings)
        db.commit()

        settings = test_list.get_field_settings()
        assert settings['quantity']['visible'] is False

    def test_list_is_field_visible(self, test_list, db):
        """Test checking if field is visible."""
        field_settings = {
            'name': {'visible': True, 'editable': True},
            'quantity': {'visible': False, 'editable': True}
        }
        test_list.set_field_settings(field_settings)
        db.commit()

        assert test_list.is_field_visible('name') is True
        assert test_list.is_field_visible('quantity') is False

    def test_list_is_field_editable(self, test_list, db):
        """Test checking if field is editable."""
        field_settings = {
            'name': {'visible': True, 'editable': True},
            'quantity': {'visible': True, 'editable': False}
        }
        test_list.set_field_settings(field_settings)
        db.commit()

        assert test_list.is_field_editable('name') is True
        assert test_list.is_field_editable('quantity') is False

    def test_list_share_with_user(self, test_list, test_user2, db):
        """Test sharing list with another user."""
        test_list.share_with_user(test_user2.id, permission='view')
        db.commit()

        # Verify the share was created
        share = ListShare.query.filter_by(
            list_id=test_list.id,
            user_id=test_user2.id
        ).first()
        assert share is not None
        assert share.permission == 'view'

    def test_list_revoke_user_access(self, test_list, test_user2, db):
        """Test revoking list access from user."""
        test_list.share_with_user(test_user2.id, permission='view')
        db.commit()

        test_list.revoke_user_access(test_user2.id)
        db.commit()

        share = ListShare.query.filter_by(
            list_id=test_list.id,
            user_id=test_user2.id
        ).first()
        assert share is None


class TestItemModel:
    """Test Item model."""

    def test_item_creation(self, test_item):
        """Test creating a new item."""
        assert test_item.id is not None
        assert test_item.name == 'Test Item'
        assert test_item.quantity == 5
        assert test_item.list_id is not None

    def test_item_to_dict(self, test_item):
        """Test item to_dict serialization."""
        item_dict = test_item.to_dict()

        assert item_dict['id'] == test_item.id
        assert item_dict['name'] == 'Test Item'
        assert item_dict['quantity'] == 5
        assert 'created_at' in item_dict

    def test_item_repr(self, test_item):
        """Test item string representation."""
        assert str(test_item) == '<Item Test Item>'

    def test_item_get_tags_list_empty(self, test_item):
        """Test getting tags list when empty."""
        tags = test_item.get_tags_list()
        assert len(tags) == 0

    def test_item_set_tags_list(self, test_item, db):
        """Test setting tags list."""
        test_item.set_tags_list(['tag1', 'tag2'])
        db.commit()

        tags = test_item.get_tags_list()
        assert len(tags) == 2
        assert 'tag1' in tags

    def test_item_low_stock_status_false(self, test_item):
        """Test low stock status when not low."""
        test_item.quantity = 10
        test_item.low_stock_threshold = 5
        assert test_item.is_low_stock is False

    def test_item_low_stock_status_true(self, test_item):
        """Test low stock status when low."""
        test_item.quantity = 2
        test_item.low_stock_threshold = 5
        assert test_item.is_low_stock is True

    def test_item_low_stock_at_threshold(self, test_item):
        """Test low stock when at threshold."""
        test_item.quantity = 5
        test_item.low_stock_threshold = 5
        assert test_item.is_low_stock is True

    def test_item_low_stock_no_threshold(self, test_item):
        """Test low stock when no threshold set."""
        test_item.quantity = 2
        test_item.low_stock_threshold = 0
        assert test_item.is_low_stock is False

    def test_item_get_custom_field_value(self, test_item, test_list, db):
        """Test getting custom field value."""
        # Create a custom field
        field = ListCustomField(
            list_id=test_list.id,
            name='Color',
            field_type='text'
        )
        db.add(field)
        db.commit()

        # Create field value
        value = ItemCustomField(
            item_id=test_item.id,
            field_id=field.id,
            value_text='Red'
        )
        db.add(value)
        db.commit()

        # Retrieve and verify
        retrieved = test_item.get_custom_field_value(field.id)
        assert retrieved is not None
        assert retrieved.value_text == 'Red'

    def test_item_get_main_image_none(self, test_item):
        """Test getting main image when no images exist."""
        main_image = test_item.get_main_image()
        assert main_image is None

    def test_item_default_quantity(self, test_list, db):
        """Test that item quantity defaults to 1."""
        item = Item(name='New Item', list_id=test_list.id)
        db.add(item)
        db.commit()

        assert item.quantity == 1

    def test_item_optional_fields(self, test_list, db):
        """Test that optional fields are nullable."""
        item = Item(name='Minimal Item', list_id=test_list.id)
        db.add(item)
        db.commit()

        assert item.description is None
        assert item.notes is None
        assert item.location is None
        assert item.barcode is None


class TestListCustomField:
    """Test ListCustomField model."""

    def test_custom_field_creation(self, test_list, db):
        """Test creating a custom field."""
        field = ListCustomField(
            list_id=test_list.id,
            name='Color',
            field_type='text'
        )
        db.add(field)
        db.commit()

        assert field.id is not None
        assert field.name == 'Color'
        assert field.field_type == 'text'
        assert field.is_visible is True
        assert field.is_editable is True

    def test_custom_field_with_options(self, test_list, db):
        """Test custom field with options."""
        options = ['Red', 'Green', 'Blue']
        field = ListCustomField(
            list_id=test_list.id,
            name='Color',
            field_type='options',
            options=options
        )
        db.add(field)
        db.commit()

        retrieved_options = field.get_options()
        assert retrieved_options == options

    def test_custom_field_repr(self, test_list, db):
        """Test custom field string representation."""
        field = ListCustomField(
            list_id=test_list.id,
            name='Color',
            field_type='text'
        )
        db.add(field)
        db.commit()

        assert str(field) == '<ListCustomField Color>'

