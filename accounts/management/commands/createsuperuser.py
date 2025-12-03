from django.core.management.base import BaseCommand
from django.contrib.auth import get_user_model
from django.db import DEFAULT_DB_ALIAS

User = get_user_model()


class Command(BaseCommand):
    help = 'Create a superuser (email 필드 없이)'

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # email 필드를 제거
        self.UserModel = User
        self.username_field = self.UserModel._meta.get_field(self.UserModel.USERNAME_FIELD)

    def add_arguments(self, parser):
        parser.add_argument(
            '--%s' % self.UserModel.USERNAME_FIELD,
            dest=self.UserModel.USERNAME_FIELD,
            default=None,
            help='슈퍼유저의 %s' % self.username_field.verbose_name,
        )
        parser.add_argument(
            '--name',
            dest='name',
            default=None,
            help='슈퍼유저의 이름',
        )
        parser.add_argument(
            '--noinput', '--no-input',
            action='store_false', dest='interactive',
            help='비대화형 모드로 실행',
        )
        parser.add_argument(
            '--database',
            action='store', dest='database',
            default=DEFAULT_DB_ALIAS,
            help='사용할 데이터베이스를 지정합니다',
        )

    def execute(self, *args, **options):
        self.stdin = options.get('stdin', self.stdin)
        return super().execute(*args, **options)

    def handle(self, *args, **options):
        username = options.get(self.UserModel.USERNAME_FIELD)
        name = options.get('name')
        database = options.get('database')

        # 비대화형 모드
        if not options.get('interactive', True):
            if not username:
                self.stdout.write(
                    self.style.ERROR('Error: --%s is required in non-interactive mode.' % self.UserModel.USERNAME_FIELD)
                )
                return
            if not name:
                self.stdout.write(
                    self.style.ERROR('Error: --name is required in non-interactive mode.')
                )
                return

        # 대화형 모드
        if options.get('interactive', True):
            try:
                if hasattr(self.stdin, 'isatty') and not self.stdin.isatty():
                    raise NotImplementedError
                username = self._get_input(self.UserModel.USERNAME_FIELD, username)
                name = self._get_input('name', name)
            except KeyboardInterrupt:
                self.stdout.write('\nOperation cancelled.')
                return
            except NotImplementedError:
                self.stdout.write(
                    self.style.ERROR('Error: Cannot create superuser in non-interactive mode.')
                )
                return

        password = None
        if options.get('interactive', True):
            password = self._get_password()

        try:
            user = self.UserModel._default_manager.db_manager(database).create_superuser(
                username=username,
                password=password,
                name=name,
            )
            self.stdout.write(
                self.style.SUCCESS('Superuser created successfully.')
            )
        except Exception as e:
            self.stdout.write(
                self.style.ERROR('Error: %s' % str(e))
            )

    def _get_input(self, field_name, default=None):
        """필드 입력 받기"""
        field = self.UserModel._meta.get_field(field_name) if field_name != 'name' else None
        verbose_name = field.verbose_name if field else '이름'
        
        while True:
            if default:
                prompt = '%s (leave blank to use \'%s\'): ' % (verbose_name, default)
            else:
                prompt = '%s: ' % verbose_name
            
            value = input(prompt)
            if default and not value:
                return default
            if value:
                return value
            self.stdout.write(self.style.ERROR('This field cannot be blank.'))

    def _get_password(self):
        """비밀번호 입력 받기"""
        from getpass import getpass
        
        password = None
        while password is None:
            password = getpass('Password: ')
            password2 = getpass('Password (again): ')
            if password != password2:
                self.stdout.write(self.style.ERROR('Error: Your passwords didn\'t match.'))
                password = None
                continue
            if not password:
                self.stdout.write(self.style.ERROR('Error: Blank passwords aren\'t allowed.'))
                password = None
                continue
        return password

