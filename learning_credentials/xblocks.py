"""XBlocks for Learning Credentials."""

import logging

from xblock.core import XBlock
from xblock.fields import Scope, String
from xblock.fragment import Fragment
from xblock.utils.resources import ResourceLoader
from xblock.utils.studio_editable import StudioEditableXBlockMixin

from .core_api import generate_credential_for_user, get_eligible_users_by_credential_type, get_user_credentials_by_type

loader = ResourceLoader(__name__)
logger = logging.getLogger(__name__)


class CredentialsXBlock(StudioEditableXBlockMixin, XBlock):
    """XBlock that displays the credential eligibility status and allows eligible users to generate credentials."""

    display_name = String(
        help='The display name for this component.',
        scope=Scope.content,
        display_name="Display name",
        default='Credentials',
    )

    def student_view(self, context) -> Fragment:  # noqa: ANN001, ARG002
        """Main view for the student. Displays the credential eligibility or ineligibility status."""
        fragment = Fragment()
        eligible_types = False
        credentials = []

        if not (is_author_mode := getattr(self.runtime, 'is_author_mode', False)):
            credentials = self.get_credentials()
            eligible_types = self.get_eligible_credential_types()

            # Filter out the eligible types that already have a credential generated
            for cred_type in credentials:
                if cred_type in eligible_types:
                    del eligible_types[cred_type]

        fragment.add_content(
            loader.render_django_template(
                'public/html/credentials_xblock.html',
                {
                    'credentials': credentials,
                    'eligible_types': eligible_types,
                    'is_author_mode': is_author_mode,
                },
            )
        )

        fragment.add_css_url(self.runtime.local_resource_url(self, "public/css/credentials_xblock.css"))
        fragment.add_javascript_url(self.runtime.local_resource_url(self, "public/js/credentials_xblock.js"))
        fragment.initialize_js('CredentialsXBlock')
        return fragment

    def get_eligible_credential_types(self) -> dict[str, bool]:
        """Retrieve the eligibility status for each credential type."""
        eligible_users = get_eligible_users_by_credential_type(self.runtime.course_id, user_id=self.scope_ids.user_id)

        return {credential_type: bool(users) for credential_type, users in eligible_users.items()}

    def get_credentials(self) -> dict[str, dict[str, str]]:
        """Retrieve the credentials for the current user in the current course."""
        return get_user_credentials_by_type(self.runtime.course_id, self.scope_ids.user_id)

    @XBlock.json_handler
    def generate_credential(self, data: dict, suffix: str = '') -> dict[str, str]:  # noqa: ARG002
        """Handler for generating a credential for a specific type."""
        credential_type = data.get('credential_type')
        if not credential_type:
            return {'status': 'error', 'message': 'No credential type specified.'}

        course_id = self.runtime.course_id
        user_id = self.scope_ids.user_id
        logger.info(
            'Generating a credential for user %s in course %s with type %s.', user_id, course_id, credential_type
        )

        try:
            generate_credential_for_user(course_id, credential_type, user_id)
        except ValueError as e:
            return {'status': 'error', 'message': str(e)}
        return {'status': 'success'}
