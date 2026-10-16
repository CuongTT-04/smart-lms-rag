from django.db import transaction
from django.db.models import Count, Q, OuterRef, Subquery, IntegerField
from django.db.models.functions import Coalesce
from django.utils import timezone
from drf_spectacular.utils import extend_schema
from rest_framework import serializers
from rest_framework.exceptions import NotFound, PermissionDenied, ValidationError
from rest_framework.response import Response

from apps.courses.models import AnnouncementComment, AnnouncementCommentVote, Classroom, ClassroomCommentMute
from apps.courses.permissions import can_manage_course
from .serializers import StrictRequestSerializer
from .session_views import ClassroomSessionsView


class CommentInput(StrictRequestSerializer):
    content = serializers.CharField(max_length=2000)
    parent_id = serializers.UUIDField(required=False, allow_null=True)


class VoteInput(StrictRequestSerializer):
    value = serializers.ChoiceField(choices=[-1, 0, 1])


class MuteInput(StrictRequestSerializer):
    is_muted = serializers.BooleanField()


class CommentSerializer(serializers.ModelSerializer):
    author_id = serializers.UUIDField(read_only=True)
    author_name = serializers.SerializerMethodField()
    author_role = serializers.CharField(source='author.role', read_only=True)
    parent_id = serializers.UUIDField(read_only=True, allow_null=True)
    is_deleted = serializers.SerializerMethodField()
    can_delete = serializers.SerializerMethodField()
    author_muted = serializers.SerializerMethodField()
    upvotes = serializers.IntegerField(read_only=True)
    downvotes = serializers.IntegerField(read_only=True)
    my_vote = serializers.IntegerField(read_only=True)

    def get_author_name(self, obj) -> str:
        return obj.author.full_name or obj.author.username

    def get_is_deleted(self, obj) -> bool:
        return obj.deleted_at is not None

    def get_can_delete(self, obj) -> bool:
        return not obj.deleted_at and (self.context['manage'] or obj.author_id == self.context['request'].user.pk)

    def get_author_muted(self, obj) -> bool:
        return obj.author_id in self.context['muted_ids']

    class Meta:
        model = AnnouncementComment
        fields = ['id', 'author_id', 'author_name', 'author_role', 'parent_id', 'content', 'created_at',
                  'is_deleted', 'can_delete', 'author_muted', 'upvotes', 'downvotes', 'my_vote']
        read_only_fields = fields


class MutedStudentSerializer(serializers.Serializer):
    id = serializers.UUIDField()
    name = serializers.CharField()


class CommentPageSerializer(serializers.Serializer):
    count = serializers.IntegerField()
    next = serializers.URLField(allow_null=True)
    previous = serializers.URLField(allow_null=True)
    results = CommentSerializer(many=True)
    can_comment = serializers.BooleanField()
    can_manage = serializers.BooleanField()
    muted_students = MutedStudentSerializer(many=True)


class CommentAccessView(ClassroomSessionsView):
    serializer_class = CommentSerializer

    def scoped_post(self, request, course_id, classroom_id, announcement_id, lock=False):
        room = self.room(request, course_id, classroom_id)
        if lock:
            Classroom.objects.select_for_update().get(pk=room.pk)
            room = self.room(request, course_id, classroom_id)
        post = room.announcements.filter(pk=announcement_id).first()
        if not post:
            raise NotFound('Không tìm thấy thông báo.')
        return room, post

    def comments(self, request, post):
        my_vote = AnnouncementCommentVote.objects.filter(comment_id=OuterRef('pk'), user=request.user).values('value')[:1]
        return post.comments.select_related('author').annotate(
            upvotes=Count('votes', filter=Q(votes__value=1)),
            downvotes=Count('votes', filter=Q(votes__value=-1)),
            my_vote=Coalesce(Subquery(my_vote), 0, output_field=IntegerField()),
        ).order_by('created_at', 'id')

    def context(self, request, room):
        return {'request': request, 'manage': can_manage_course(request.user, room.course),
                'muted_ids': set(room.comment_mutes.values_list('user_id', flat=True))}

    def comment(self, request, post, comment_id):
        item = self.comments(request, post).filter(pk=comment_id).first()
        if not item:
            raise NotFound('Không tìm thấy bình luận.')
        return item


class AnnouncementCommentsView(CommentAccessView):
    http_method_names = ['get', 'post', 'head', 'options']

    @extend_schema(tags=['Classrooms'], summary='Xem bình luận của thông báo', description='Thành viên lớp xem bình luận, trả lời và số lượt bình chọn. Giáo viên xem thêm danh sách học viên bị mute.', responses={200: CommentPageSerializer})
    def get(self, request, course_id, classroom_id, announcement_id):
        room, post = self.scoped_post(request, course_id, classroom_id, announcement_id)
        context = self.context(request, room)
        page = self.paginate_queryset(self.comments(request, post))
        response = self.get_paginated_response(CommentSerializer(page, many=True, context=context).data)
        response.data.update(can_comment=request.user.pk not in context['muted_ids'], can_manage=context['manage'])
        response.data['muted_students'] = [
            {'id': str(mute.user_id), 'name': mute.user.full_name or mute.user.username}
            for mute in room.comment_mutes.select_related('user').order_by('created_at', 'pk')
        ] if context['manage'] else []
        return response

    @extend_schema(tags=['Classrooms'], summary='Gửi bình luận hoặc trả lời', description='Thành viên lớp gửi nội dung tối đa 2000 ký tự. Học viên bị mute không được gửi; bình luận cha phải thuộc cùng thông báo.', request=CommentInput, responses={201: CommentSerializer})
    @transaction.atomic
    def post(self, request, course_id, classroom_id, announcement_id):
        room, post = self.scoped_post(request, course_id, classroom_id, announcement_id, lock=True)
        context = self.context(request, room)
        if request.user.pk in context['muted_ids']:
            raise PermissionDenied('Bạn đã bị tắt quyền bình luận trong lớp này.')
        data = CommentInput(data=request.data)
        data.is_valid(raise_exception=True)
        parent_id = data.validated_data.get('parent_id')
        if parent_id and not post.comments.filter(pk=parent_id, deleted_at__isnull=True).exists():
            raise ValidationError({'parent_id': 'Bình luận gốc không còn khả dụng hoặc thuộc thông báo khác.'})
        item = AnnouncementComment.objects.create(announcement=post, author=request.user, **data.validated_data)
        return Response(CommentSerializer(self.comment(request, post, item.pk), context=context).data, status=201)


class AnnouncementCommentDetailView(CommentAccessView):
    http_method_names = ['delete', 'options']

    @extend_schema(tags=['Classrooms'], summary='Xóa bình luận', description='Học viên chỉ xóa bình luận của mình; chủ khóa học được xóa bình luận trong lớp. Giữ chỗ và các câu trả lời, xóa nội dung và lượt vote.', responses={204: None})
    @transaction.atomic
    def delete(self, request, course_id, classroom_id, announcement_id, comment_id):
        room, post = self.scoped_post(request, course_id, classroom_id, announcement_id, lock=True)
        item = self.comment(request, post, comment_id)
        if item.author_id != request.user.pk and not can_manage_course(request.user, room.course):
            raise PermissionDenied('Bạn chỉ có thể xóa bình luận của mình.')
        item.content = ''
        item.deleted_at = timezone.now()
        item.save(update_fields=['content', 'deleted_at'])
        item.votes.all().delete()
        return Response(status=204)


class AnnouncementCommentVoteView(CommentAccessView):
    http_method_names = ['put', 'options']

    @extend_schema(tags=['Classrooms'], summary='Bình chọn bình luận', description='Gửi 1 để upvote, -1 để downvote, 0 để bỏ vote. Mỗi thành viên có một lượt cho mỗi bình luận.', request=VoteInput, responses=CommentSerializer)
    @transaction.atomic
    def put(self, request, course_id, classroom_id, announcement_id, comment_id):
        room, post = self.scoped_post(request, course_id, classroom_id, announcement_id, lock=True)
        item = self.comment(request, post, comment_id)
        if item.deleted_at:
            raise ValidationError('Bình luận đã bị xóa.')
        data = VoteInput(data=request.data)
        data.is_valid(raise_exception=True)
        value = data.validated_data['value']
        if value:
            AnnouncementCommentVote.objects.update_or_create(comment=item, user=request.user, defaults={'value': value})
        else:
            item.votes.filter(user=request.user).delete()
        return Response(CommentSerializer(self.comment(request, post, item.pk), context=self.context(request, room)).data)


class ClassroomCommentMuteView(ClassroomSessionsView):
    http_method_names = ['put', 'options']

    @extend_schema(tags=['Classrooms'], summary='Mute hoặc bỏ mute học viên', description='Chủ khóa học tắt hoặc khôi phục quyền bình luận và trả lời của học viên trong toàn bộ bảng tin lớp. Học viên vẫn xem được bảng tin.', request=MuteInput, responses={200: MuteInput})
    @transaction.atomic
    def put(self, request, course_id, classroom_id, user_id):
        room = self.room(request, course_id, classroom_id, manage=True)
        Classroom.objects.select_for_update().get(pk=room.pk)
        room = self.room(request, course_id, classroom_id, manage=True)
        data = MuteInput(data=request.data)
        data.is_valid(raise_exception=True)
        if data.validated_data['is_muted']:
            if not room.enrollments.filter(student__user_id=user_id, student__user__role='STUDENT', status__in=['ACTIVE', 'COMPLETED']).exists():
                raise ValidationError('Học viên không thuộc lớp này.')
            ClassroomCommentMute.objects.get_or_create(classroom=room, user_id=user_id, defaults={'muted_by': request.user})
        else:
            room.comment_mutes.filter(user_id=user_id).delete()
        return Response(data.validated_data)
